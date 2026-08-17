# mailtm-otp

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)]()

This library is used to create a temporary inbox and read incoming emails
programmatically. It automatically creates temp emails, waits for an OTP,
and extracts the OTP.

## Example

```python
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
```

## Prerequisites

- **Python 3.10+**
- **(Optional) `uv` package manager:** For convenience, you can use [Astral UV](https://astral.sh/docs/uv) to manage dependencies. Install via `pip install uv` and use `uv sync` as shown below. Alternatively, you may install dependencies with pip manually.

## Installation

```bash
pip install git+https://github.com/rakin406/mailtm-otp.git
```  
*Alternatively*, use the `uv` manager:  
```bash
uv add git+https://github.com/rakin406/mailtm-otp.git
```

## Contributing

Contributions, bug reports, and feature requests are welcome! Feel free to open an issue or submit a pull request on GitHub.

## Contact

Rakin Rahman - rakinrahman406@gmail.com

## License

This project is released under the **MIT License** (see the [LICENSE](LICENSE) file). 
