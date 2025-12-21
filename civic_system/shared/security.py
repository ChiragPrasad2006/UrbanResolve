# shared/security.py
import random


def generate_otp() -> str:
    """
    Generates a 6-digit numeric OTP as string.
    """
    return str(random.randint(100000, 999999))
