from mailtm_otp import MailTmClient, MailTmError

if __name__ == "__main__":
    client = MailTmClient()
    email, password = client.create_account()
    print(f"Created temp mailbox: {email} (password: {password})")
    print("Waiting up to 2 minutes for an OTP email...")

    try:
        otp = client.wait_for_otp(timeout=120)
        print(f"OTP found: {otp}")
    except MailTmError as e:
        print(f"Failed: {e}")
