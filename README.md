# Abijah's Field Measurements

### Setup Development Environment

Prerequisites: Python 3.7+ (when dicts became ordered by insertion)

```sh
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

### Start Server

Within the virtualenv:

```sh
. venv/bin/activate
# FLASK_ENV=development FLASK_APP=server flask run
FLASK_DEBUG=1 FLASK_APP=server flask run
```
