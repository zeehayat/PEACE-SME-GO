# Chapter 9: Uploads, S3-Compatible Storage, and Media References

## Purpose

The portal stores documents and audio/video media in S3-compatible storage. The database stores references to public object URLs. In this chapter, we will learn about S3 object storage APIs, presigned URLs, and how to safely integrate S3 client packages in Go.

---

## Theoretical Background

### Object Storage vs. Block/File Storage
Unlike traditional filesystems which organize data into hierarchical nested directories (Block/File storage), **Object Storage** stores data as flat objects within a single bucket:
- An object consists of the file data, a unique string identifier (the **Object Key**), and metadata (such as `Content-Type`, file size, or custom tags).
- Objects are accessed via HTTP API calls (GET/PUT/DELETE requests).
- S3-compatible providers (like AWS, MinIO, Backblaze B2, Contabo) offer highly scalable flat storage structures, making them ideal for handling unstructured assets like images, PDFs, and videos.

### Presigned URLs
In standard multipart uploads, a client sends the file to the backend, which in turn streams the bytes to S3 storage. This consumes substantial backend CPU, memory, and bandwidth.
- **Presigned URLs** delegate access permissions cryptographically.
- The backend uses its secret credentials to generate a temporary, signed HTTP URL (e.g., valid for 15 minutes) for a specific S3 key.
- The client uploads the file directly to S3 via a PUT request to that URL.
- This bypasses the backend for file streaming, saving significant server resources.

```text
[ Client ] --- 1. Request Upload URL ---> [ Go Backend ]
[ Client ] <--- 2. Presigned PUT URL ------ [ Go Backend ]
[ Client ] --- 3. HTTP PUT File ---------> [ S3 / Object Storage ]
[ Client ] --- 4. Confirm Upload --------> [ Go Backend (Write DB reference) ]
```

### Upload Validation and Security
- **MIME-Type Validation:** Never trust the client-supplied file extension. In production systems, read the first 512 bytes of the upload payload (magic bytes) to verify the MIME-Type accurately.
- **Path Traversal Prevention:** When storing files locally or naming keys on S3, clean the file names using helpers like `filepath.Base()` to prevent directory traversal exploits.
- **Authorization Verification:** Before generating a presigned URL, verify the authenticated user has write permissions for that specific business or grant directory.

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
