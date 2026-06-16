#### ENDPOINTS #####

 Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/user/profile` | — | `{user_id, email_address, first_name, last_name, cnic, language, gender, mobile_no, ...}` |
| GET | `/business` | — | Business profile row or `{}` |
| POST | `/business` | Business profile fields (see schema) | `{message, business_id}` |
| PUT | `/business` | Business profile fields | `{message}` |
| POST | `/upload-document/<business_id>` | multipart/form-data: `file`, `document_type` | `{message, file_path}` |
| POST | `/business/media/generate-upload-url` | `{file_name, mime_type, media_category}` | `{upload_url, object_key}` |
| POST | `/business/media/save-reference` | `{object_key, file_name, mime_type, document_type}` | `{message, document_id}` |
| GET | `/grant` | — | Grant row + `access_state` field |
| POST | `/grant` | Full grant form payload (see schema) | `{message, grant_id}` |
| PUT | `/grant` | Grant form fields | `{message}` |
| GET | `/grant-status` | — | `{status, approved_amount, approval_reason}` |
| POST | `/grant/generate-upload-url` | `{file_name, mime_type}` | `{upload_url, object_key}` |
| POST | `/grant/save-media-reference` | `{object_key, file_name, mime_type, media_type}` | `{message, media_id}` |


### PARALLEL LEARNING NOTES ###

| Feature | Go Concept                    | Vue concept               | Git concept       |
|---------|-------------------------------|---------------------------|-------------------|
| Login   | structs, bycrypt, JWT, errors | form state, localStorage3 | small auth branch |
|         |                               |                           |                   |
