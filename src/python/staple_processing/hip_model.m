% Remove clear so workspace vars from Python persist
clc; close all;

addpath(genpath('STAPLE'));

%----------%
% SETTINGS %
%----------%¨

if exist('output_models_folder_in', 'var')
    output_models_folder = output_models_folder_in;
else
    output_models_folder = '';
end

% folder where the various datasets (and their geometries) are located.
% Used as fallback if tri_folder is not provided directly.
datasets_folder = 'data';

% dataset(s) that you would like to process specified as cell array. 
dataset_set = {'test'};
body_mass = 64; %kg

% cell array with the name of the bone geometries to process.
bones_list = {'pelvis_no_sacrum', 'femur_r', 'tibia_r'};

% format of visualization geometry (obj preferred - smaller files)
vis_geom_format = 'obj'; % options: 'stl'/'obj'

% choose the definition of the joint coordinate systems (see
% documentation). For hip joint creation this option has no effect.
joint_defs = 'auto2020';
%--------------------------------------

% create model folder if required
if ~isfolder(output_models_folder); mkdir(output_models_folder); end

% setup for batch processing
for n_d = 1:numel(dataset_set)
    
    % dataset id used to name OpenSim model and setup folders
    cur_dataset = dataset_set{n_d};
    
    % infer body side
    cur_side = inferBodySideFromAnatomicStruct(bones_list);
    
    % model name
    cur_model_name = [joint_defs,'_hip_', upper(cur_side)];
    
    % set output model name
    output_model_file_name = 'bone_model.osim'
    
    % log printout
    log_file = fullfile(output_models_folder, [cur_model_name, '.log']);
    logConsolePrintout('on', log_file);
    
    % folder including the bone geometries in MATLAB format ('tri'/'stl')
    if exist('tri_folder_in', 'var')
        tri_folder = tri_folder_in;
    else
        tri_folder = fullfile(datasets_folder, cur_dataset, 'stl');
    end
    
    % create TriGeomSet structure for the specified geometries
    geom_set = createTriGeomSet(bones_list, tri_folder);
    
    % create bone geometry folder for visualization
    geometry_folder_name = 'Geometry';
    geometry_folder_path = fullfile(output_models_folder,geometry_folder_name);
    writeModelGeometriesFolder(geom_set, geometry_folder_path, vis_geom_format);
    
    % process bone geometries (compute joint parameters and identify markers)
    [JCS, BL, CS] = processTriGeomBoneSet(geom_set);
    
    % initialize OpenSim model
    osimModel = initializeOpenSimModel(cur_model_name);
    
    % create bodies
    osimModel = addBodiesFromTriGeomBoneSet(osimModel, geom_set, geometry_folder_name, vis_geom_format);

    % create joints
    createOpenSimModelJoints(osimModel, JCS, joint_defs);

    % update mass properties to those estimated using a scale version of
    % gait2392 with COM based on Winterss book.
    osimModel = assignMassPropsToSegments(osimModel, JCS, body_mass);
    
    % add markers to the bones
    addBoneLandmarksAsMarkers(osimModel, BL);
    
    % finalize connections
    osimModel.finalizeConnections();
    
    % print OpenSim model
    osimModel.print(fullfile(output_models_folder, output_model_file_name));
    
    % inform the user about time employed to create the model
    disp('-------------------------')
    disp(['Model generated in ', sprintf('%.1f', toc), ' s']);
    disp(['Saved as ', fullfile(output_models_folder, output_model_file_name),'.']);
    disp(['Model geometries saved in folder: ', geometry_folder_path,'.'])
    disp('-------------------------')
    logConsolePrintout('off');
end

% remove paths
rmpath(genpath('msk-STAPLE/STAPLE'));