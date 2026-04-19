import open3d as o3d
import numpy as np
import pyvista as pv
from scipy.spatial import cKDTree
from probreg import cpd
import argparse
import os

def load_and_sample_mesh(filepath, num_points=3000):
    mesh = o3d.io.read_triangle_mesh(filepath)
    mesh.compute_vertex_normals()
    pcd = mesh.sample_points_uniformly(number_of_points=num_points)
    return mesh, pcd

def load_vtk_attachment(filepath):
    vtk_data = pv.read(filepath)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(vtk_data.points)
    return pcd

def export_to_legacy_vtk(pcd, output_path):
    points = np.asarray(pcd.points)
    num_points = len(points)
    with open(output_path, 'w') as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write("vtk output\nASCII\nDATASET POLYDATA\n")
        f.write(f"POINTS {num_points} float\n")
        for i, pt in enumerate(points):
            f.write(f"{pt[0]:.6f} {pt[1]:.6f} {pt[2]:.6f} ")
            if (i + 1) % 3 == 0: f.write("\n")
        if num_points % 3 != 0: f.write("\n")
        f.write(f"VERTICES {num_points} {num_points * 2}\n")
        for i in range(num_points): f.write(f"1 {i} \n")
        f.write(f"\nCELL_DATA {num_points}\nPOINT_DATA {num_points}\n")
        f.write("SCALARS scalars bit\nLOOKUP_TABLE default\n")
        for i in range(num_points):
            f.write("1" + ("\n" if (i + 1) % 8 == 0 or i == num_points - 1 else " "))

def process_bone_attachments(lhdl_bone, target_bone, lhdl_attachments, outputs):
    ref_mesh, ref_pcd = load_and_sample_mesh(lhdl_bone)
    target_mesh, target_pcd = load_and_sample_mesh(target_bone)
    
    # 1. Rigid ICP (Point-to-Plane) s rotací
    ref_center = ref_pcd.get_center()
    target_center = target_pcd.get_center()
    
    # Pro pelvic bones a femur/tibia můžeme potřebovat jinou výchozí rotaci (zde zanecháváme tvou Z 180)
    R_z = np.array([[-1., 0., 0.], [0., -1., 0.], [0., 0., 1.]])
    ref_pcd.rotate(R_z, center=ref_center)
    
    trans_init = np.eye(4)
    trans_init[0:3, 3] = target_center - ref_center
    
    reg_p2p = o3d.pipelines.registration.registration_icp(
        ref_pcd, target_pcd, 100.0, trans_init,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=5000)
    )
    ref_pcd.transform(reg_p2p.transformation)
    
    # 2. Elastické CPD
    original_ref_points = np.asarray(ref_pcd.points).copy()
    tf_param, _, _ = cpd.registration_cpd(source=ref_pcd, target=target_pcd, tf_type_name='nonrigid', maxiter=150)
    deformed_ref_points = tf_param.transform(original_ref_points)
    
    displacements = deformed_ref_points - original_ref_points
    tree_lhdl = cKDTree(original_ref_points)
    
    target_vertices = np.asarray(target_mesh.vertices)
    tree_target = cKDTree(target_vertices)
    
    # 3. Zpracování všech úponů pro tuto kost v cyklu
    for att_path, out_path in zip(lhdl_attachments, outputs):
        att_pcd = load_vtk_attachment(att_path)
        att_pcd.rotate(R_z, center=ref_center)
        att_pcd.transform(reg_p2p.transformation)
        
        orig_att_pts = np.asarray(att_pcd.points)
        final_points = []
        for pt in orig_att_pts:
            # Prostorová interpolace z deformované kosti
            _, indices = tree_lhdl.query(pt, k=3)
            mean_disp = np.mean(displacements[indices], axis=0)
            new_pt = pt + mean_disp
            # Přisátí na .stl
            _, t_idx = tree_target.query(new_pt)
            final_points.append(target_vertices[t_idx])
            
        final_pcd = o3d.geometry.PointCloud()
        final_pcd.points = o3d.utility.Vector3dVector(np.array(final_points))
        export_to_legacy_vtk(final_pcd, out_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lhdl-bone", required=True)
    parser.add_argument("--target-bone", required=True)
    parser.add_argument("--lhdl-attachments", nargs='+', required=True)
    parser.add_argument("--outputs", nargs='+', required=True)
    args = parser.parse_args()
    
    process_bone_attachments(args.lhdl_bone, args.target_bone, args.lhdl_attachments, args.outputs)