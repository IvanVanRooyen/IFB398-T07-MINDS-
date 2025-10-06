# File upload
from pathlib import Path  

MEDIA_URL = "/media/"
MEDIA_ROOT = str(BASE_DIR / "media") 
FILE_UPLOAD_PERMISSIONS = 0o640