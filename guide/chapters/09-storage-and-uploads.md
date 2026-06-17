# Chapter 9: Uploads, S3-Compatible Storage, and Media References

## Purpose

The portal stores business documents (CNIC, bank statements, certificates) and grant media (audio/video recordings) in S3-compatible object storage. The database stores only references — public URLs — to these objects. This chapter teaches multipart form handling in Go, presigned URL generation with the AWS SDK v2, file security validation, and the two upload patterns used by the portal.

---

## Concepts: Object Storage

### What Is Object Storage?

Unlike a local filesystem with folders and files, object storage is flat. Every file is an "object" identified by a unique key within a bucket.

```
Bucket: peace-economic
│
├── business_42/cnic_front.pdf         ← object key
├── business_42/cnic_back.pdf
├── business_42/bank_statement.pdf
├── grant_42/recording_video.mp4
└── status_docs/decision_42.pdf
```

Object metadata:
- **Key**: the unique path-like identifier
- **Content-Type**: MIME type (e.g., `application/pdf`, `image/jpeg`)
- **ACL**: Access Control List (`public-read` makes the object accessible via a public URL)

### Public URL Construction

```
S3_PUBLIC_BASE_URL = https://eu2.contabostorage.com/peace-economic
Object Key         = business_42/cnic_front.pdf
Public URL         = https://eu2.contabostorage.com/peace-economic/business_42/cnic_front.pdf
```

The database stores the full public URL in `business_documents.file_path` and `grant_media.file_path`.

### Path-Style vs Virtual-Hosted-Style Addressing

AWS S3 uses virtual-hosted-style:
```
https://bucket-name.s3.amazonaws.com/key
```

S3-compatible providers (Contabo, MinIO, Backblaze) use path-style:
```
https://eu2.contabostorage.com/bucket-name/key
```

The Go AWS SDK v2 must be configured to force path-style addressing for non-AWS providers:

```go
s3.NewFromConfig(sdkCfg, func(o *s3.Options) {
    o.UsePathStyle = true  // Required for Contabo, MinIO, etc.
})
```

---

## The Two Upload Patterns

The portal uses two distinct upload patterns for different scenarios:

### Pattern 1: Direct Multipart Upload Through Backend

```
[Client]                    [Go Backend]                [S3]
   |                              |                       |
   |  POST /api/upload-document   |                       |
   |  Content-Type: multipart/    |                       |
   |  form-data                   |                       |
   | ─────────────────────────> |                       |
   |                              | PutObject(key, data) |
   |                              | ────────────────────>|
   |                              |                       |
   |                              |      200 OK          |
   |                              | <────────────────────|
   |                              |                       |
   |  {message, file_path}       |                       |
   | <──────────────────────── |                       |
```

**Use for**: CNIC images, certificates, bank statements — smaller files where the admin or applicant uploads from a form directly.

**Endpoint**: `POST /api/upload-document/:business_id`

### Pattern 2: Presigned PUT URL — Direct to S3

```
[Client]                    [Go Backend]                [S3]
   |                              |                       |
   | POST /generate-upload-url   |                       |
   | ─────────────────────────> |                       |
   |                              |  PresignPutObject()  |
   |                              | (signs URL, no S3 call yet)
   |                              |                       |
   |  {upload_url, object_key}   |                       |
   | <──────────────────────── |                       |
   |                              |                       |
   |  PUT upload_url (directly)  |                       |
   | ─────────────────────────────────────────────────> |
   |                              |                       |
   |  200 OK from S3             |                       |
   | <─────────────────────────────────────────────────|
   |                              |                       |
   | POST /save-media-reference  |                       |
   | {object_key, file_name, ...}|                       |
   | ─────────────────────────> |                       |
   |                              | INSERT INTO db       |
   |                              |                       |
   |  {message, document_id}     |                       |
   | <──────────────────────── |                       |
```

**Use for**: Large audio/video recordings — the backend never streams the file data.

**Endpoints**:
1. `POST /api/business/media/generate-upload-url` or `POST /api/grant/generate-upload-url`
2. `POST /api/business/media/save-reference` or `POST /api/grant/save-media-reference`

---

## Database Tables for Storage References

### business_documents

```sql
CREATE TABLE business_documents (
    document_id    SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    business_id    INTEGER NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    document_type  VARCHAR(100),   -- 'CNIC (front)', 'Bank statement', etc.
    file_name      TEXT,           -- original filename
    file_path      TEXT,           -- S3 public URL
    mime_type      VARCHAR(100),
    uploaded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### grant_media

```sql
CREATE TABLE grant_media (
    media_id    SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    business_id INTEGER NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    grant_id    INTEGER NOT NULL REFERENCES grants(grant_id) ON DELETE CASCADE,
    media_type  VARCHAR(10),    -- 'video' or 'audio'
    file_name   TEXT,
    file_path   TEXT UNIQUE,    -- S3 public URL (UNIQUE enforced)
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Required Document Types

The "fully verified" report checks for all five required types:

```go
// internal/storage/document_types.go
package storage

// RequiredDocumentTypes are the five document types an applicant must upload.
var RequiredDocumentTypes = []string{
    "CNIC (front)",
    "CNIC (back)",
    "Business registration certificate",
    "Tax certificate / NTN",
    "Bank statement",
}

// ValidDocumentTypes is the full set of allowed document_type values.
var ValidDocumentTypes = map[string]bool{
    "CNIC (front)":                     true,
    "CNIC (back)":                      true,
    "Business registration certificate": true,
    "Tax certificate / NTN":            true,
    "Bank statement":                   true,
    "Other supporting document":        true,
}

// ValidMediaTypes are the allowed media_type values for grant_media.
var ValidMediaTypes = map[string]bool{
    "video": true,
    "audio": true,
}

// AllowedMIMETypes are the MIME types the portal accepts for document uploads.
var AllowedMIMETypes = map[string]bool{
    "image/jpeg":         true,
    "image/png":          true,
    "application/pdf":    true,
    "image/jpg":          true,
}

// AllowedMediaMIMETypes are the MIME types accepted for audio/video media.
var AllowedMediaMIMETypes = map[string]bool{
    "video/mp4":     true,
    "video/webm":    true,
    "audio/mpeg":    true,
    "audio/mp4":     true,
    "audio/webm":    true,
    "audio/ogg":     true,
}

// MaxDocumentSizeBytes is the maximum allowed file size for documents (10 MB).
const MaxDocumentSizeBytes = 10 * 1024 * 1024

// MaxMediaSizeBytes is the maximum allowed file size for media (200 MB).
const MaxMediaSizeBytes = 200 * 1024 * 1024
```

---

## The S3 Client Implementation

```go
// internal/storage/s3.go
package storage

import (
    "context"
    "fmt"
    "io"
    "strings"
    "time"

    "github.com/aws/aws-sdk-go-v2/aws"
    awsconfig "github.com/aws/aws-sdk-go-v2/config"
    "github.com/aws/aws-sdk-go-v2/credentials"
    "github.com/aws/aws-sdk-go-v2/service/s3"
)

// S3Config holds the S3-compatible storage configuration.
type S3Config struct {
    EndpointURL   string
    AccessKey     string
    SecretKey     string
    BucketName    string
    PublicBaseURL string
    UploadACL     string
}

// Client wraps the AWS SDK S3 client with helper methods.
type Client struct {
    s3Client      *s3.Client
    presignClient *s3.PresignClient
    bucketName    string
    publicBaseURL string
    uploadACL     string
}

// NewClient initialises an S3 client configured for an S3-compatible provider.
func NewClient(cfg S3Config) (*Client, error) {
    if cfg.EndpointURL == "" {
        return nil, fmt.Errorf("S3 endpoint URL is required")
    }

    // Custom endpoint resolver for non-AWS S3-compatible providers (Contabo, MinIO, etc.)
    customResolver := aws.EndpointResolverWithOptionsFunc(
        func(service, region string, options ...interface{}) (aws.Endpoint, error) {
            return aws.Endpoint{
                URL:               cfg.EndpointURL,
                SigningRegion:     "us-east-1",
                HostnameImmutable: true,
            }, nil
        },
    )

    sdkCfg, err := awsconfig.LoadDefaultConfig(context.Background(),
        awsconfig.WithCredentialsProvider(
            credentials.NewStaticCredentialsProvider(cfg.AccessKey, cfg.SecretKey, ""),
        ),
        awsconfig.WithEndpointResolverWithOptions(customResolver),
        awsconfig.WithRegion("us-east-1"),
    )
    if err != nil {
        return nil, fmt.Errorf("failed to load S3 SDK config: %w", err)
    }

    // UsePathStyle=true is required for Contabo, MinIO, and most S3-compatible providers
    s3c := s3.NewFromConfig(sdkCfg, func(o *s3.Options) {
        o.UsePathStyle = true
    })

    return &Client{
        s3Client:      s3c,
        presignClient: s3.NewPresignClient(s3c),
        bucketName:    cfg.BucketName,
        publicBaseURL: strings.TrimRight(cfg.PublicBaseURL, "/"),
        uploadACL:     cfg.UploadACL,
    }, nil
}

// UploadObject uploads a file directly to S3.
// Use this for the multipart form upload pattern.
func (c *Client) UploadObject(ctx context.Context, key, contentType string, body io.Reader) error {
    _, err := c.s3Client.PutObject(ctx, &s3.PutObjectInput{
        Bucket:      aws.String(c.bucketName),
        Key:         aws.String(key),
        ContentType: aws.String(contentType),
        Body:        body,
        ACL:         s3Types.ObjectCannedACLPublicRead,
    })
    if err != nil {
        return fmt.Errorf("S3 PutObject failed for key %q: %w", key, err)
    }
    return nil
}

// GeneratePresignedPutURL creates a temporary URL the client can use to upload directly.
// Use this for the presigned URL pattern (large files, media recordings).
func (c *Client) GeneratePresignedPutURL(ctx context.Context, key, contentType string, expiry time.Duration) (string, error) {
    req, err := c.presignClient.PresignPutObject(ctx, &s3.PutObjectInput{
        Bucket:      aws.String(c.bucketName),
        Key:         aws.String(key),
        ContentType: aws.String(contentType),
    }, func(o *s3.PresignerOptions) {
        o.Expires = expiry
    })
    if err != nil {
        return "", fmt.Errorf("S3 presign failed for key %q: %w", key, err)
    }
    return req.URL, nil
}

// BuildPublicURL constructs the permanent public URL for an object key.
func (c *Client) BuildPublicURL(key string) string {
    return fmt.Sprintf("%s/%s", c.publicBaseURL, key)
}

// GetKeyFromURL extracts the object key from a full public URL.
func (c *Client) GetKeyFromURL(publicURL string) string {
    prefix := c.publicBaseURL + "/"
    return strings.TrimPrefix(publicURL, prefix)
}

// DeleteObject removes an object from S3 given its full public URL.
func (c *Client) DeleteObject(ctx context.Context, publicURL string) error {
    key := c.GetKeyFromURL(publicURL)
    _, err := c.s3Client.DeleteObject(ctx, &s3.DeleteObjectInput{
        Bucket: aws.String(c.bucketName),
        Key:    aws.String(key),
    })
    if err != nil {
        return fmt.Errorf("S3 DeleteObject failed for key %q: %w", key, err)
    }
    return nil
}
```

---

## Object Key Generation

Generate consistent, collision-resistant object keys:

```go
// internal/storage/keys.go
package storage

import (
    "fmt"
    "path/filepath"
    "strings"
    "time"
)

// BusinessDocumentKey generates a key for a business document.
// Format: business_<id>/<type>_<timestamp>.<ext>
func BusinessDocumentKey(businessID int64, documentType, filename string) string {
    ext := filepath.Ext(filename)
    safeType := strings.ReplaceAll(strings.ToLower(documentType), " ", "_")
    safeType = strings.ReplaceAll(safeType, "/", "_")
    ts := time.Now().UnixMilli()
    return fmt.Sprintf("business_%d/%s_%d%s", businessID, safeType, ts, ext)
}

// GrantMediaKey generates a key for grant audio/video media.
// Format: grant_<id>/media_<timestamp>.<ext>
func GrantMediaKey(grantID int64, filename string) string {
    ext := filepath.Ext(filename)
    ts := time.Now().UnixMilli()
    return fmt.Sprintf("grant_%d/media_%d%s", grantID, ts, ext)
}

// StatusDocumentKey generates a key for admin-uploaded supporting documents.
func StatusDocumentKey(userID int64, filename string) string {
    ext := filepath.Ext(filename)
    ts := time.Now().UnixMilli()
    return fmt.Sprintf("status_docs/user_%d_%d%s", userID, ts, ext)
}
```

---

## Security: Validation Before Upload

Never trust the client for file type or safety. Always validate on the server.

```go
// internal/storage/validation.go
package storage

import (
    "fmt"
    "net/http"
    "path/filepath"
    "strings"
)

// ValidateUpload checks that a file is safe to upload.
// It detects content type from magic bytes, not the client-provided content-type.
func ValidateUpload(filename string, data []byte, maxBytes int64, allowedMIMEs map[string]bool) (string, error) {
    // 1. Prevent path traversal: strip directory components from the filename
    safeName := filepath.Base(filename)
    if safeName == "." || safeName == ".." || safeName == "" {
        return "", fmt.Errorf("invalid filename")
    }

    // 2. Check file size (data is already read by the caller with a size limit)
    if int64(len(data)) > maxBytes {
        return "", fmt.Errorf("file size %d bytes exceeds maximum of %d bytes", len(data), maxBytes)
    }

    // 3. Detect actual content type from the first 512 bytes (magic bytes)
    // This prevents MIME type spoofing (e.g., renaming a PHP script to .jpg)
    detectedType := http.DetectContentType(data[:min(512, len(data))])

    // http.DetectContentType may return types with parameters (e.g. "text/plain; charset=utf-8")
    // Strip parameters for the lookup
    mimeBase := strings.Split(detectedType, ";")[0]
    mimeBase = strings.TrimSpace(mimeBase)

    if !allowedMIMEs[mimeBase] {
        return "", fmt.Errorf("file type %q is not allowed", mimeBase)
    }

    return mimeBase, nil
}

func min(a, b int) int {
    if a < b {
        return a
    }
    return b
}

// SafeFilename returns the base filename, preventing path traversal.
func SafeFilename(clientFilename string) string {
    return filepath.Base(clientFilename)
}
```

---

## Pattern 1: Multipart Upload Handler

```go
// internal/storage/handler.go
package storage

import (
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strconv"

    "peace-sme-go/internal/middleware"
)

// DocumentRepository handles saving document references to PostgreSQL.
type DocumentRepository interface {
    UpsertDocument(ctx context.Context, doc Document) (int64, error)
    OwnsBusinessID(ctx context.Context, userID, businessID int64) (bool, error)
}

// Document represents a row to insert/update in business_documents.
type Document struct {
    UserID       int64
    BusinessID   int64
    DocumentType string
    FileName     string
    FilePath     string   // S3 public URL
    MimeType     string
}

// Handler provides upload endpoint handlers.
type Handler struct {
    s3   *Client
    repo DocumentRepository
}

func NewHandler(s3 *Client, repo DocumentRepository) *Handler {
    return &Handler{s3: s3, repo: repo}
}

// UploadDocument handles POST /api/upload-document/:business_id
// This is the direct multipart upload pattern.
func (h *Handler) UploadDocument(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    // Extract business_id from URL
    businessIDStr := r.PathValue("business_id") // Go 1.22+ PathValue
    businessID, err := strconv.ParseInt(businessIDStr, 10, 64)
    if err != nil {
        jsonError(w, "invalid business_id", http.StatusBadRequest)
        return
    }

    // 1. Ownership check: user must own this business
    owns, err := h.repo.OwnsBusinessID(r.Context(), userID, businessID)
    if err != nil || !owns {
        jsonError(w, "access denied", http.StatusForbidden)
        return
    }

    // 2. Parse multipart form with size limit (10MB max)
    r.Body = http.MaxBytesReader(w, r.Body, MaxDocumentSizeBytes)
    if err := r.ParseMultipartForm(MaxDocumentSizeBytes); err != nil {
        jsonError(w, "file too large or invalid form", http.StatusRequestEntityTooLarge)
        return
    }

    // 3. Get form fields
    documentType := r.FormValue("document_type")
    if !ValidDocumentTypes[documentType] {
        jsonError(w, fmt.Sprintf("invalid document_type: %q", documentType), http.StatusBadRequest)
        return
    }

    // 4. Get uploaded file
    file, header, err := r.FormFile("file")
    if err != nil {
        jsonError(w, "no file uploaded", http.StatusBadRequest)
        return
    }
    defer file.Close()

    // 5. Read file content (with size limit already applied by MaxBytesReader)
    data, err := io.ReadAll(file)
    if err != nil {
        jsonError(w, "failed to read file", http.StatusBadRequest)
        return
    }

    // 6. Validate file type from magic bytes
    mimeType, err := ValidateUpload(header.Filename, data, MaxDocumentSizeBytes, AllowedMIMETypes)
    if err != nil {
        jsonError(w, err.Error(), http.StatusUnsupportedMediaType)
        return
    }

    // 7. Generate object key and upload to S3
    key := BusinessDocumentKey(businessID, documentType, SafeFilename(header.Filename))
    if err := h.s3.UploadObject(r.Context(), key, mimeType, bytesReader(data)); err != nil {
        jsonError(w, "upload to storage failed", http.StatusInternalServerError)
        return
    }

    // 8. Build public URL and save reference to database
    publicURL := h.s3.BuildPublicURL(key)
    doc := Document{
        UserID:       userID,
        BusinessID:   businessID,
        DocumentType: documentType,
        FileName:     SafeFilename(header.Filename),
        FilePath:     publicURL,
        MimeType:     mimeType,
    }
    docID, err := h.repo.UpsertDocument(r.Context(), doc)
    if err != nil {
        jsonError(w, "failed to save document reference", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message":     "Document uploaded successfully",
        "file_path":   publicURL,
        "document_id": docID,
    })
}

func bytesReader(data []byte) *bytesReaderT {
    return &bytesReaderT{data: data, pos: 0}
}

type bytesReaderT struct {
    data []byte
    pos  int
}

func (b *bytesReaderT) Read(p []byte) (int, error) {
    if b.pos >= len(b.data) {
        return 0, io.EOF
    }
    n := copy(p, b.data[b.pos:])
    b.pos += n
    return n, nil
}

func jsonError(w http.ResponseWriter, msg string, code int) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(code)
    json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
```

---

## Pattern 2: Presigned URL Handler

```go
// internal/storage/presign_handler.go
package storage

import (
    "encoding/json"
    "fmt"
    "net/http"
    "path/filepath"
    "time"

    "peace-sme-go/internal/middleware"
)

// GenerateUploadURLRequest is the body for presigned URL generation endpoints.
type GenerateUploadURLRequest struct {
    FileName      string `json:"file_name"`
    MimeType      string `json:"mime_type"`
    MediaCategory string `json:"media_category"` // for business media
}

// SaveReferenceRequest is the body for saving a pre-uploaded object reference.
type SaveReferenceRequest struct {
    ObjectKey    string `json:"object_key"`
    FileName     string `json:"file_name"`
    MimeType     string `json:"mime_type"`
    DocumentType string `json:"document_type"`  // for business docs
    MediaType    string `json:"media_type"`      // for grant media: "video" or "audio"
}

// GenerateBusinessMediaUploadURL handles POST /api/business/media/generate-upload-url
func (h *Handler) GenerateBusinessMediaUploadURL(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req GenerateUploadURLRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        jsonError(w, "invalid request body", http.StatusBadRequest)
        return
    }

    // Validate MIME type
    if !AllowedMIMETypes[req.MimeType] && !AllowedMediaMIMETypes[req.MimeType] {
        jsonError(w, fmt.Sprintf("MIME type %q is not allowed", req.MimeType), http.StatusBadRequest)
        return
    }

    // Build a safe, unique object key
    safeName := SafeFilename(req.FileName)
    ext := filepath.Ext(safeName)
    key := fmt.Sprintf("business_media/user_%d_%d%s", userID, time.Now().UnixMilli(), ext)

    // Generate presigned URL valid for 60 minutes
    uploadURL, err := h.s3.GeneratePresignedPutURL(r.Context(), key, req.MimeType, 60*time.Minute)
    if err != nil {
        jsonError(w, "failed to generate upload URL", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{
        "upload_url": uploadURL,
        "object_key": key,
    })
}

// SaveBusinessMediaReference handles POST /api/business/media/save-reference
func (h *Handler) SaveBusinessMediaReference(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req SaveReferenceRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        jsonError(w, "invalid request body", http.StatusBadRequest)
        return
    }

    // Validate document type
    if req.DocumentType != "" && !ValidDocumentTypes[req.DocumentType] {
        jsonError(w, "invalid document_type", http.StatusBadRequest)
        return
    }

    // Build public URL from object key
    publicURL := h.s3.BuildPublicURL(req.ObjectKey)

    // Get the business for this user
    bizID, err := h.repo.GetBusinessIDForUser(r.Context(), userID)
    if err != nil {
        jsonError(w, "no business profile found", http.StatusBadRequest)
        return
    }

    doc := Document{
        UserID:       userID,
        BusinessID:   bizID,
        DocumentType: req.DocumentType,
        FileName:     SafeFilename(req.FileName),
        FilePath:     publicURL,
        MimeType:     req.MimeType,
    }
    docID, err := h.repo.UpsertDocument(r.Context(), doc)
    if err != nil {
        jsonError(w, "failed to save document reference", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message":     "Media reference saved",
        "document_id": docID,
    })
}

// GenerateGrantMediaUploadURL handles POST /api/grant/generate-upload-url
func (h *Handler) GenerateGrantMediaUploadURL(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req GenerateUploadURLRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        jsonError(w, "invalid request body", http.StatusBadRequest)
        return
    }

    if !AllowedMediaMIMETypes[req.MimeType] {
        jsonError(w, fmt.Sprintf("MIME type %q is not allowed for grant media", req.MimeType), http.StatusBadRequest)
        return
    }

    // Get grant ID for this user
    grantID, err := h.repo.GetGrantIDForUser(r.Context(), userID)
    if err != nil {
        jsonError(w, "no grant application found", http.StatusBadRequest)
        return
    }

    key := GrantMediaKey(grantID, SafeFilename(req.FileName))
    uploadURL, err := h.s3.GeneratePresignedPutURL(r.Context(), key, req.MimeType, 60*time.Minute)
    if err != nil {
        jsonError(w, "failed to generate upload URL", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{
        "upload_url": uploadURL,
        "object_key": key,
    })
}

// SaveGrantMediaReference handles POST /api/grant/save-media-reference
func (h *Handler) SaveGrantMediaReference(w http.ResponseWriter, r *http.Request) {
    userID := middleware.MustUserID(r.Context())

    var req SaveReferenceRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        jsonError(w, "invalid request body", http.StatusBadRequest)
        return
    }

    // Validate media type
    if !ValidMediaTypes[req.MediaType] {
        jsonError(w, "media_type must be 'video' or 'audio'", http.StatusBadRequest)
        return
    }

    publicURL := h.s3.BuildPublicURL(req.ObjectKey)

    bizID, _ := h.repo.GetBusinessIDForUser(r.Context(), userID)
    grantID, _ := h.repo.GetGrantIDForUser(r.Context(), userID)

    media := GrantMedia{
        UserID:     userID,
        BusinessID: bizID,
        GrantID:    grantID,
        MediaType:  req.MediaType,
        FileName:   SafeFilename(req.FileName),
        FilePath:   publicURL,
    }
    mediaID, err := h.repo.InsertGrantMedia(r.Context(), media)
    if err != nil {
        jsonError(w, "failed to save media reference", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusCreated)
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message":  "Media reference saved",
        "media_id": mediaID,
    })
}
```

---

## The Storage Repository

```go
// internal/storage/repository.go
package storage

import (
    "context"
    "fmt"

    "github.com/jackc/pgx/v5/pgxpool"
)

// GrantMedia represents a row in grant_media.
type GrantMedia struct {
    UserID     int64
    BusinessID int64
    GrantID    int64
    MediaType  string
    FileName   string
    FilePath   string
}

type PostgresRepository struct {
    db *pgxpool.Pool
}

func NewPostgresRepository(db *pgxpool.Pool) *PostgresRepository {
    return &PostgresRepository{db: db}
}

// UpsertDocument inserts or updates a business_documents row.
// On conflict (business_id, document_type), updates the existing row.
func (r *PostgresRepository) UpsertDocument(ctx context.Context, doc Document) (int64, error) {
    query := `
        INSERT INTO business_documents (user_id, business_id, document_type, file_name, file_path, mime_type)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (business_id, document_type)
        DO UPDATE SET
            file_name  = EXCLUDED.file_name,
            file_path  = EXCLUDED.file_path,
            mime_type  = EXCLUDED.mime_type,
            uploaded_at = CURRENT_TIMESTAMP
        RETURNING document_id
    `
    var docID int64
    err := r.db.QueryRow(ctx, query,
        doc.UserID, doc.BusinessID, doc.DocumentType,
        doc.FileName, doc.FilePath, doc.MimeType,
    ).Scan(&docID)
    if err != nil {
        return 0, fmt.Errorf("UpsertDocument: %w", err)
    }
    return docID, nil
}

// OwnsBusinessID checks if a user owns a specific business.
func (r *PostgresRepository) OwnsBusinessID(ctx context.Context, userID, businessID int64) (bool, error) {
    var count int
    err := r.db.QueryRow(ctx,
        "SELECT COUNT(*) FROM businesses WHERE user_id=$1 AND business_id=$2",
        userID, businessID,
    ).Scan(&count)
    if err != nil {
        return false, fmt.Errorf("OwnsBusinessID: %w", err)
    }
    return count > 0, nil
}

// GetBusinessIDForUser returns the business_id for a user.
func (r *PostgresRepository) GetBusinessIDForUser(ctx context.Context, userID int64) (int64, error) {
    var bizID int64
    err := r.db.QueryRow(ctx,
        "SELECT business_id FROM businesses WHERE user_id=$1",
        userID,
    ).Scan(&bizID)
    if err != nil {
        return 0, fmt.Errorf("GetBusinessIDForUser: %w", err)
    }
    return bizID, nil
}

// GetGrantIDForUser returns the grant_id for a user.
func (r *PostgresRepository) GetGrantIDForUser(ctx context.Context, userID int64) (int64, error) {
    var grantID int64
    err := r.db.QueryRow(ctx,
        "SELECT grant_id FROM grants WHERE user_id=$1",
        userID,
    ).Scan(&grantID)
    if err != nil {
        return 0, fmt.Errorf("GetGrantIDForUser: %w", err)
    }
    return grantID, nil
}

// InsertGrantMedia inserts a row into grant_media.
func (r *PostgresRepository) InsertGrantMedia(ctx context.Context, m GrantMedia) (int64, error) {
    query := `
        INSERT INTO grant_media (user_id, business_id, grant_id, media_type, file_name, file_path)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING media_id
    `
    var mediaID int64
    err := r.db.QueryRow(ctx, query,
        m.UserID, m.BusinessID, m.GrantID, m.MediaType, m.FileName, m.FilePath,
    ).Scan(&mediaID)
    if err != nil {
        return 0, fmt.Errorf("InsertGrantMedia: %w", err)
    }
    return mediaID, nil
}
```

---

## The Cleanup Endpoint

The Flask app has a cleanup endpoint that removes duplicate business_documents rows. The Go equivalent:

```go
// POST /api/admin/maintenance/cleanup-duplicates
func (h *AdminHandler) CleanupDuplicateDocuments(w http.ResponseWriter, r *http.Request) {
    query := `
        DELETE FROM business_documents
        WHERE document_id NOT IN (
            SELECT DISTINCT ON (business_id, document_type) document_id
            FROM business_documents
            ORDER BY business_id, document_type, uploaded_at DESC
        )
    `
    result, err := h.db.Exec(r.Context(), query)
    if err != nil {
        jsonError(w, "cleanup failed", http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]interface{}{
        "message":      "Duplicate documents cleaned up",
        "removed_count": result.RowsAffected(),
    })
}
```

---

## Testing the Presigned URL Generation

```go
// internal/storage/s3_test.go
package storage_test

import (
    "context"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
    "time"

    "peace-sme-go/internal/storage"
)

func TestGeneratePresignedPutURL_ContainsKey(t *testing.T) {
    // Use a mock S3 server (MinIO in tests, or mock the presign function)
    // For unit testing, we test the URL structure
    cfg := storage.S3Config{
        EndpointURL:   "http://localhost:9000",
        AccessKey:     "minioadmin",
        SecretKey:     "minioadmin",
        BucketName:    "test-bucket",
        PublicBaseURL: "http://localhost:9000/test-bucket",
    }

    client, err := storage.NewClient(cfg)
    if err != nil {
        t.Fatalf("failed to create client: %v", err)
    }

    ctx := context.Background()
    key := "business_1/cnic_front_12345.pdf"
    url, err := client.GeneratePresignedPutURL(ctx, key, "application/pdf", 60*time.Minute)
    if err != nil {
        t.Fatalf("GeneratePresignedPutURL failed: %v", err)
    }

    if !strings.Contains(url, key) {
        t.Errorf("presigned URL should contain the object key %q, got %q", key, url)
    }
    if !strings.Contains(url, "X-Amz-Signature") {
        t.Errorf("presigned URL should contain X-Amz-Signature, got %q", url)
    }
}

func TestValidateUpload_RejectsMismatchedMIME(t *testing.T) {
    // PNG magic bytes disguised as a PDF
    pngBytes := []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A}
    // Pad to 512 bytes
    for len(pngBytes) < 512 {
        pngBytes = append(pngBytes, 0x00)
    }

    allowed := map[string]bool{"application/pdf": true}
    _, err := storage.ValidateUpload("document.pdf", pngBytes, storage.MaxDocumentSizeBytes, allowed)
    if err == nil {
        t.Error("expected error for PNG data presented as PDF, got nil")
    }
}

func TestValidateUpload_AcceptsValidPDF(t *testing.T) {
    // Real PDF magic bytes: %PDF-
    pdfBytes := []byte{'%', 'P', 'D', 'F', '-', '1', '.', '4'}
    for len(pdfBytes) < 512 {
        pdfBytes = append(pdfBytes, 0x20)
    }

    allowed := map[string]bool{"application/pdf": true}
    mimeType, err := storage.ValidateUpload("document.pdf", pdfBytes, storage.MaxDocumentSizeBytes, allowed)
    if err != nil {
        t.Errorf("expected success for valid PDF, got: %v", err)
    }
    if !strings.HasPrefix(mimeType, "application/pdf") {
        t.Errorf("expected application/pdf, got %q", mimeType)
    }
}

func TestBuildPublicURL(t *testing.T) {
    cfg := storage.S3Config{
        EndpointURL:   "http://localhost:9000",
        AccessKey:     "key",
        SecretKey:     "secret",
        BucketName:    "peace-economic",
        PublicBaseURL: "https://eu2.contabostorage.com/peace-economic",
    }
    client, _ := storage.NewClient(cfg)

    url := client.BuildPublicURL("business_42/cnic_front.pdf")
    expected := "https://eu2.contabostorage.com/peace-economic/business_42/cnic_front.pdf"
    if url != expected {
        t.Errorf("expected %q, got %q", expected, url)
    }
}

func TestGetKeyFromURL(t *testing.T) {
    cfg := storage.S3Config{
        EndpointURL:   "http://localhost:9000",
        AccessKey:     "key",
        SecretKey:     "secret",
        BucketName:    "peace-economic",
        PublicBaseURL: "https://eu2.contabostorage.com/peace-economic",
    }
    client, _ := storage.NewClient(cfg)

    fullURL := "https://eu2.contabostorage.com/peace-economic/business_42/cnic_front.pdf"
    key := client.GetKeyFromURL(fullURL)
    expected := "business_42/cnic_front.pdf"
    if key != expected {
        t.Errorf("expected key %q, got %q", expected, key)
    }
}
```

---

## Presigned URL Flow — Vue Frontend Side

For completeness, here is how the Vue frontend uses the presigned URL pattern. Understanding this confirms the API contract your Go handlers must satisfy:

```javascript
// In RecordingCapture.vue — after recording is complete
const uploadRecording = async (blob, mimeType) => {
    const token = localStorage.getItem('userToken');
    const ext = mimeType.includes('video') ? '.mp4' : '.webm';
    const fileName = `recording_${Date.now()}${ext}`;
    const mediaType = mimeType.includes('video') ? 'video' : 'audio';

    // Step 1: Get presigned URL from our Go backend
    const { data } = await axios.post(
        `${API_BASE_URL}/api/grant/generate-upload-url`,
        { file_name: fileName, mime_type: mimeType },
        { headers: { Authorization: `Bearer ${token}` } }
    );
    // data = { upload_url: "https://s3.../...", object_key: "grant_42/media_..." }

    // Step 2: PUT directly to S3 using the presigned URL
    await axios.put(data.upload_url, blob, {
        headers: { 'Content-Type': mimeType },
    });
    // The file is now in S3 — our backend was not involved

    // Step 3: Tell our backend to save the reference in the database
    await axios.post(
        `${API_BASE_URL}/api/grant/save-media-reference`,
        {
            object_key: data.object_key,
            file_name: fileName,
            mime_type: mimeType,
            media_type: mediaType,
        },
        { headers: { Authorization: `Bearer ${token}` } }
    );
    // data = { message: "Media reference saved", media_id: 7 }
};
```

This confirms:
1. `generate-upload-url` returns `{upload_url, object_key}`
2. The client PUTs directly to S3 (no auth header in that request)
3. `save-media-reference` receives `{object_key, file_name, mime_type, media_type}`

---

## Mastery Check

You understand this chapter when you can:

1. Explain the difference between the two upload patterns and when to use each — specifically why large audio/video recordings should use presigned URLs instead of streaming through the backend.
2. Write a Go handler for `POST /api/upload-document/:business_id` that: enforces a 10MB size limit with `http.MaxBytesReader`, reads the multipart form, detects the MIME type from magic bytes using `http.DetectContentType`, rejects disallowed types, generates an S3 object key, uploads with `PutObject`, and saves the public URL in `business_documents`.
3. Configure an AWS SDK v2 S3 client for an S3-compatible provider using `UsePathStyle=true` and a custom endpoint resolver.
4. Implement `BuildPublicURL` and `GetKeyFromURL` and explain why the database stores the full public URL rather than just the object key.
5. Write a test for `ValidateUpload` that verifies PNG magic bytes are rejected when only `application/pdf` is in the allowed MIME types map.
