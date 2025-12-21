# shared/email_utils.py
def send_email(to_email: str, subject: str, body: str):
    """
    Simulated email sender.
    Prints email content to terminal.
    Replace with SMTP later if needed.
    """
    print("\n================ EMAIL =================")
    print(f"TO      : {to_email}")
    print(f"SUBJECT : {subject}")
    print("---------------------------------------")
    print(body)
    print("=======================================\n")
