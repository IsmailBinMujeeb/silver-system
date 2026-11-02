# Deployment notes (Render)

## Before making this public
- Confirm you have permission to publish the tender PDFs and their contents. This project ZIP includes 13 PDFs and a search database built from them.
- The app has no login/authentication. Anyone who can reach a public deployment may search the indexed content and open PDFs via `/documents/...`.
- Render's default filesystem is ephemeral. Uploads and database changes may be lost on restart/redeploy unless you configure persistent storage and back up the database/documents.
- OCR is not included. Pages without extractable text will not be searchable.

## Deploy
1. Push the `tender_document_search` folder contents to a GitHub repository (the folder containing `app.py`, `requirements.txt`, `render.yaml`, `templates/`, `static/`, `documents/`, and `data/`).
2. In Render, choose **New + → Blueprint** and connect the repository containing `render.yaml`.
3. Review the service settings and deploy.
4. Test search and PDF viewing using the generated Render URL.

Do not publish company-confidential PDFs or source code without approval. For a public demo, consider replacing the included tender PDFs with documents approved for public sharing and adding authentication before enabling uploads.
