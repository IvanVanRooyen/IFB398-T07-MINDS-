import hashlib

def md5_for_upload(django_file) -> str:
    hasher = hashlib.md5()
    for chunk in django_file.chunks():
        hasher.update(chunk)
    return hasher.hexdigest()
