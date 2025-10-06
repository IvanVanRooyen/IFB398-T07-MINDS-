import hashlib

from django.contrib.gis.db import models


def sha256_file(django_file) -> str:
    pos = django_file.tell()
    django_file.seek(0)

    h = hashlib.sha256()

    for chunk in iter(lambda: django_file.read(8192), b""):
        h.update(chunk)
    django_file.seek(pos)

    return h.hexdigest()



# class AutoConstraintMeta(type(models.Model)):
#     """
#     Metaclass to automatically generate constraints for choice field validation
#     """
#
#     def __new__(mcs, name, bases, namespace, **kwargs):
#         cls: models.Model = super().__new__(mcs, name, bases, namespace, **kwargs)
#
#         if namespace.get("Meta") and getattr(namespace["Meta"], "abstract", False):
#             return cls
#
#         if not hasattr(cls._meta, "constraints"):
#             cls._meta.constraints = []
#
#         for field in cls._meta.fields:
#             if field.choices and not any(
#                 field.name in str(c.check) for c in cls._meta.constraints
#             ):
#                 constraint = choice_constraint(
#                     field.name,
#                     field.choices,
#                     f"valid_{cls._meta.db_table}_{field.name}",
#                 )
#                 cls._meta.constraints.append(constraint)
#
#         return cls


# class AutoConstrainedModel(ValidatedChoiceModel,):
#     class Meta:
#         abstract = True
