from django.contrib.auth.hashers import Argon2PasswordHasher


class ServiceArgon2Hasher(Argon2PasswordHasher):
    time_cost = 2
    memory_cost = 19456
    parallelism = 1
