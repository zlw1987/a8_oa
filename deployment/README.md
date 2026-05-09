# Deployment Notes

This folder contains helper files and operational notes for deploying the A8 OA Django app.

## Files

- `godaddy-git-version-control-guide.md`: Step-by-step GoDaddy cPanel Git Version Control setup.
- `passenger_wsgi.py.example`: Reference Passenger WSGI startup file for the cPanel Python App.

## Current GoDaddy Test Target

```text
Domain: 4z8.d4d.mytemp.website
App URL: /oa-test
App root: /home/rsnwvvl103hc/a8_oa
Startup file: passenger_wsgi.py
Entry point: application
```

The recommended deployment flow is:

```text
Local Git -> GitHub -> GoDaddy Git Version Control -> Deploy HEAD Commit -> Python App restart
```
