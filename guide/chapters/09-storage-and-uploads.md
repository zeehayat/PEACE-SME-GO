# Chapter 9: Uploads, S3-Compatible Storage, and Media References

## Purpose

The portal stores documents and audio/video media in S3-compatible storage. The database stores references to public object URLs. In this chapter, we will learn about S3 object storage APIs, presigned URLs, and how to safely integrate S3 client packages in Go.

---

## Foundational Concepts Explained Simply

### 1. Object Storage & Presigned URLs

:::expandable [Object Storage & Presigned URLs]
#### In-Depth Explanation
Unlike local file storage which depends on nested folder paths and filesystem drivers, **Object Storage** stores unstructured files flat inside a namespace called a **Bucket**.
* **Object Key:** The unique identifier for a file (e.g. `business_42/cnic_front.pdf`).
* **Metadata:** File descriptors (e.g. `Content-Type: application/pdf`).
* **Presigning URLs:** Standard uploads stream file bytes from the client to the server, which then streams them to S3. This consumes significant server memory and bandwidth.
  * To solve this, the server generates a **Presigned URL**.
  * The server uses its private S3 API access credentials to compute a cryptographic HMAC signature containing the bucket, key, HTTP method (PUT), and an expiration timestamp.
  * The client receives this temporary URL and uploads the file directly to S3 via HTTP PUT.
  * The backend never handles the file data stream.

#### Sandbox Program: Presigned URL Mock Signature Generator
This sandbox program demonstrates how a backend computes a signed, expiring URL using HMAC, simulating the exact cryptographical delegation of permissions to a client for direct uploading:

```go
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"time"
)

// GenerateMockPresignedURL signs the bucket and key with an expiration window
func GenerateMockPresignedURL(endpoint, bucket, key, method string, expiry time.Time, secretKey []byte) string {
	// 1. Format the string that defines the permission scope
	rawURL := fmt.Sprintf("%s/%s/%s", endpoint, bucket, key)
	stringToSign := fmt.Sprintf("METHOD:%s\nURL:%s\nEXPIRY:%d", method, rawURL, expiry.Unix())

	// 2. Generate HMAC signature
	h := hmac.New(sha256.New, secretKey)
	h.Write([]byte(stringToSign))
	signature := hex.EncodeToString(h.Sum(nil))

	// 3. Assemble final URL containing query parameters
	return fmt.Sprintf("%s?method=%s&expires=%d&signature=%s",
		rawURL, method, expiry.Unix(), signature)
}

func main() {
	endpoint := "https://s3.peace-economic.storage"
	bucket := "grant-uploads"
	key := "business_42/bank_statement.pdf"
	secretKey := []byte("s3-private-storage-secret-key-999")

	// Set URL expiration to 15 minutes in the future
	expiry := time.Now().Add(15 * time.Minute)

	presignedURL := GenerateMockPresignedURL(endpoint, bucket, key, "PUT", expiry, secretKey)
	fmt.Println("Generated Presigned URL for direct file upload:")
	fmt.Println(presignedURL)
}
```
:::

### 2. Upload Validation and Security

:::expandable [Upload Validation & Security]
#### In-Depth Explanation
* **MIME-Type Verification:** Never rely on the file extension (e.g. `.jpg`) sent by the client. An attacker could rename a malicious script to `exploit.jpg` and bypass extension-only filters.
  * **Solution:** Read the first 512 bytes of the file and pass it to Go's `http.DetectContentType(...)` function to verify the actual file signature (magic bytes).
* **Path Traversal Prevention:** Always clean custom object names or filesystem targets using `filepath.Base(...)` to strip out path modifiers (like `../`) that could let attackers overwrite system files.

#### Sandbox Program: Content Type Detection & Safe Path Base
This program reads mock binary data (magic bytes) to accurately detect MIME types and cleans filenames to prevent path traversal exploits:

```go
package main

import (
	"fmt"
	"net/http"
	"path/filepath"
)

func DetectSafeFile(clientFilename string, data []byte) (string, string) {
	// 1. Prevent Path Traversal (e.g., "../../etc/passwd" -> "passwd")
	safeName := filepath.Base(clientFilename)

	// 2. Detect Content Type from magic bytes (first 512 bytes)
	detectedType := http.DetectContentType(data)

	return safeName, detectedType
}

func main() {
	// A mock malicious upload request
	unsafePath := "../../../var/www/uploads/shell.php.png"
	
	// PNG Magic bytes: 89 50 4E 47 0D 0A 1A 0A
	pngMagicBytes := []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00}

	safeName, contentType := DetectSafeFile(unsafePath, pngMagicBytes)
	fmt.Println("Original Filename:", unsafePath)
	fmt.Println("Sanitised Safe Filename:", safeName)
	fmt.Println("Detected Content-Type from bytes:", contentType)
}
```
:::

### External Resources
- [AWS S3 Presigned URL Overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html)
- [MinIO Go Client SDK Documentation](https://min.io/docs/minio/linux/developers/go-sdk.html)
- [OWASP File Upload Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

---

## Endpoints

Business:

| Method | Path |
|---|---|
| POST | `/api/upload-document/<business_id>` |
| POST | `/api/business/media/generate-upload-url` |
| POST | `/api/business/media/save-reference` |

Grant:

| Method | Path |
|---|---|
| POST | `/api/grant/generate-upload-url` |
| POST | `/api/grant/save-media-reference` |

Applicant status:

| Method | Path |
|---|---|
| POST | `/api/admin/applicant-status/generate-upload-url` |

---

## Two Upload Patterns

The app supports:
1. Multipart upload through backend.
2. Presigned URL upload directly to S3, followed by saving a DB reference.

Presigned upload is better for large media because the backend does not stream the whole file.

---

## S3 Concepts

Learn:
- Bucket.
- Object key.
- Content type.
- ACL.
- Presigned PUT URL.
- Public base URL.
- Path-style addressing for S3-compatible providers.

---

## Database Rows

Business documents:

```sql
business_documents(document_type, file_name, file_path, mime_type)
```

Grant media:

```sql
grant_media(media_type, file_name, file_path)
```

`file_path` is a public URL. Your Go storage package should know how to convert an object key into that URL.

---

## Required Documents

The reports use these required document types:
- CNIC front
- CNIC back
- Business registration certificate
- Tax certificate / NTN
- Bank statement

Make document type values consistent across upload and reporting code.

---

## Practical Examples

### Example: Generating a Presigned PUT URL in Go
This complete implementation demonstrates how to configure an S3 client and generate a secure presigned URL for direct file uploads:

```go
// File: internal/storage/s3.go
package storage

import (
	"context"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type S3Client struct {
	client        *s3.Client
	presignClient *s3.PresignClient
	bucketName    string
	publicBaseURL string
}

type S3Config struct {
	EndpointURL   string
	AccessKey     string
	SecretKey     string
	BucketName    string
	PublicBaseURL string
}

func NewS3Client(cfg S3Config) (*S3Client, error) {
	// Configure credentials and endpoints for S3-compatible providers
	customResolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
		return aws.Endpoint{
			URL:           cfg.EndpointURL,
			SigningRegion: "us-east-1",
		}, nil
	})

	sdkCfg, err := config.LoadDefaultConfig(context.Background(),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(cfg.AccessKey, cfg.SecretKey, "")),
		config.WithEndpointResolverWithOptions(customResolver),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to load S3 SDK config: %w", err)
	}

	client := s3.NewFromConfig(sdkCfg, func(o *s3.Options) {
		o.UsePathStyle = true
	})
	
	presignClient := s3.NewPresignClient(client)

	return &S3Client{
		client:        client,
		presignClient: presignClient,
		bucketName:    cfg.BucketName,
		publicBaseURL: cfg.PublicBaseURL,
	}, nil
}

// GeneratePresignedUploadURL creates a temporary PUT URL.
func (s *S3Client) GeneratePresignedUploadURL(ctx context.Context, objectKey string, contentType string, expiry time.Duration) (string, error) {
	input := &s3.PutObjectInput{
		Bucket:      aws.String(s.bucketName),
		Key:         aws.String(objectKey),
		ContentType: aws.String(contentType),
	}

	presignedReq, err := s.presignClient.PresignPutObject(ctx, input, func(o *s3.PresignerOptions) {
		o.Expires = expiry
	})
	if err != nil {
		return "", fmt.Errorf("failed to generate presigned URL: %w", err)
	}

	return presignedReq.URL, nil
}

// BuildPublicURL constructs the final public asset address.
func (s *S3Client) BuildPublicURL(objectKey string) string {
	return fmt.Sprintf("%s/%s", s.publicBaseURL, objectKey)
}
```

---

## Security Checks

Before saving a reference:
- Verify the authenticated user owns the business.
- Verify the grant belongs to the authenticated user.
- Validate media type as `audio` or `video`.
- Validate MIME type allow-lists.
- Avoid trusting client-provided public URLs; prefer object keys and build URLs server-side.

---

## Mastery Check

You understand this chapter when you can:
- Generate a presigned S3 PUT URL.
- Save an uploaded file reference to PostgreSQL.
- Explain why direct-to-S3 uploads reduce backend load.
- Enforce ownership before saving media.
- Build a public object URL from an object key.
