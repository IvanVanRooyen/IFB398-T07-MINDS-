import hashlib
def sha256_file(django_file) -> str:
    pos = django_file.tell()
    django_file.seek(0)
    h = hashlib.sha256()
    for chunk in iter(lambda: django_file.read(8192), b""):
        h.update(chunk)
    django_file.seek(pos)
    return h.hexdigest()
