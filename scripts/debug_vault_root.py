"""Debug VAULT_ROOT path resolution."""
from pathlib import Path

api_file = Path('apps/api/src/physics_vault_api/legacy_app.py').resolve()
API_ROOT = api_file.parents[1]
VAULT_ROOT_old = API_ROOT.parents[1]
VAULT_ROOT_new = API_ROOT.parents[2]
print(f'api_file = {api_file}')
print(f'API_ROOT = {API_ROOT}')
print(f'VAULT_ROOT (parents[1] OLD) = {VAULT_ROOT_old}')
print(f'VAULT_ROOT (parents[2] NEW) = {VAULT_ROOT_new}')
print(f'VAULT_ROOT_new exists = {VAULT_ROOT_new.exists()}')
img = VAULT_ROOT_new / 'data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png'
print(f'image at new path = {img.exists()}')
print(f'  path = {img}')
img2 = VAULT_ROOT_old / 'data/assets/questions/2007-GK-BJ-PHY-01-Q00000001-01.png'
print(f'image at old path = {img2.exists()}')
