import inspect, snakemake.benchmark as b
# Má vůbec BenchmarkTimer?
for name in ['BenchmarkTimer', 'benchmarked', 'BenchmarkRecord', 'write_benchmark_records']:
    obj = getattr(b, name, None)
    print(f"{name}: {'EXISTS' if obj else 'MISSING'}")

# Importuje se psutil na úrovni modulu?
import ast, textwrap
src = inspect.getsource(b)
tree = ast.parse(src)
psutil_imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                  and any(getattr(a, 'name', getattr(n, 'module', '')) == 'psutil'
                          for a in getattr(n, 'names', [n]))]
print(f'psutil imports count: {len(psutil_imports)}')
print(f"Has BENCHMARK_INTERVAL: {hasattr(b, 'BENCHMARK_INTERVAL')}")
if hasattr(b, 'BENCHMARK_INTERVAL'):
    print(f'BENCHMARK_INTERVAL = {b.BENCHMARK_INTERVAL}')