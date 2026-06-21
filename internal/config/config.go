package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config models application environment variables.
type Config struct {
	Port        int
	FrontendURL string

	// Auth
	JWTSecret  string
	AdminUsers []AdminUser

	// Database
	DatabaseURL string
	DBPoolMin   int
	DBPoolMax   int

	// Redis
	RedisURL string

	// S3
	S3EndpointURL   string
	S3AccessKey     string
	S3SecretKey     string
	S3BucketName    string
	S3PublicBaseURL string
	S3UploadACL     string

	// Email
	EmailAPIKey               string
	SenderEmail               string
	SenderName                string
	ApprovalNotificationEmail string

	// Feature toggles
	GrantApplicationOpen  bool
	GrantRequireSelection bool
	HFCShadowMode         bool
	HFCAsyncEnabled       bool
	HFCDebounceSec        int

	// Access control
	AccessControlEnabled bool
	MaxActiveApplicants  int
	AccessSlotTTLSec     int
	GeoBlockEnabled      bool
	AllowedCountryCodes  map[string]bool

	// Cache
	CacheEnabled    bool
	CachePrefix     string
	CacheTTLUpdates int
	CacheTTLFAQs    int
	CacheTTLFilters int
}

// AdminUser matches the schema of ADMIN_USERS_JSON configuration values.
type AdminUser struct {
	Username         string `json:"username"`
	PasswordHash     string `json:"password_hash"`
	Role             string `json:"role"`
	CanApproveGrants bool   `json:"can_approve_grants"`
}

func Load() (*Config, error) {
	cfg := &Config{
		AllowedCountryCodes: make(map[string]bool),
	}

	// --- Server ---
	port, err := envInt("PORT", 8080)
	if err != nil {
		return nil, err
	}
	cfg.Port = port
	cfg.FrontendURL = getEnv("FRONTEND_URL", "http://localhost:3001")

	// --- Auth ---
	cfg.JWTSecret = os.Getenv("JWT_SECRET_KEY")
	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("required env var JWT_SECRET_KEY is empty")
	}
	if len(cfg.JWTSecret) < 16 {
		return nil, fmt.Errorf("JWT_SECRET_KEY must be at least 16 characters")
	}

	adminJSON := os.Getenv("ADMIN_USERS_JSON")
	if adminJSON != "" {
		var admins []AdminUser
		if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
			return nil, fmt.Errorf("ADMIN_USERS_JSON is invalid JSON: %w", err)
		}
		if len(admins) == 0 {
			return nil, fmt.Errorf("ADMIN_USERS_JSON must contain at least one admin user")
		}
		for i, a := range admins {
			if a.Username == "" {
				return nil, fmt.Errorf("ADMIN_USERS_JSON[%d]: username is empty", i)
			}
			if a.PasswordHash == "" {
				return nil, fmt.Errorf("ADMIN_USERS_JSON[%d]: password_hash is empty", i)
			}
		}
		cfg.AdminUsers = admins
	}

	// --- Database ---
	dbHost := getEnv("POSTGRES_HOST", "localhost")
	dbPort := getEnv("POSTGRES_PORT", "5432")
	dbUser := getEnv("POSTGRES_USER", "sme_user")
	dbPass := getEnv("POSTGRES_PASSWORD", "sme_password")
	dbName := getEnv("POSTGRES_DB", "sme_app")
	cfg.DatabaseURL = fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		dbUser, dbPass, dbHost, dbPort, dbName)

	cfg.DBPoolMin, err = envInt("DB_POOL_MIN_CONN", 2)
	if err != nil {
		return nil, err
	}
	cfg.DBPoolMax, err = envInt("DB_POOL_MAX_CONN", 40)
	if err != nil {
		return nil, err
	}

	// --- Redis ---
	cfg.RedisURL = getEnv("REDIS_URL", "redis://localhost:6379/0")

	// --- S3 ---
	cfg.S3EndpointURL = os.Getenv("S3_ENDPOINT_URL")
	if cfg.S3EndpointURL == "" {
		return nil, fmt.Errorf("required env var S3_ENDPOINT_URL is empty")
	}
	cfg.S3AccessKey = os.Getenv("S3_ACCESS_KEY")
	if cfg.S3AccessKey == "" {
		return nil, fmt.Errorf("required env var S3_ACCESS_KEY is empty")
	}
	cfg.S3SecretKey = os.Getenv("S3_SECRET_KEY")
	if cfg.S3SecretKey == "" {
		return nil, fmt.Errorf("required env var S3_SECRET_KEY is empty")
	}
	cfg.S3BucketName = getEnv("S3_BUCKET_NAME", "peace-economic")
	cfg.S3PublicBaseURL = os.Getenv("S3_PUBLIC_BASE_URL")
	if cfg.S3PublicBaseURL == "" {
		return nil, fmt.Errorf("required env var S3_PUBLIC_BASE_URL is empty")
	}
	cfg.S3UploadACL = getEnv("S3_UPLOAD_ACL", "public-read")

	// --- Email ---
	cfg.EmailAPIKey = os.Getenv("EMAIL_API_KEY")
	if cfg.EmailAPIKey == "" {
		return nil, fmt.Errorf("required env var EMAIL_API_KEY is empty")
	}
	cfg.SenderEmail = getEnv("SENDER_EMAIL", "info@srsp.cloud")
	cfg.SenderName = getEnv("SENDER_NAME", "PEACE SME GRANT")
	cfg.ApprovalNotificationEmail = os.Getenv("APPROVAL_NOTIFICATION_EMAIL")

	// --- Feature Toggles ---
	cfg.GrantApplicationOpen = getEnv("GRANT_APPLICATION_OPEN", "0") == "1"
	cfg.GrantRequireSelection = getEnv("GRANT_REQUIRE_SELECTION", "1") == "1"
	cfg.HFCShadowMode = getEnv("HFC_SHADOW_MODE", "1") == "1"
	cfg.HFCAsyncEnabled = getEnv("HFC_ASYNC_ENABLED", "1") == "1"

	cfg.HFCDebounceSec, err = envInt("HFC_ENQUEUE_DEBOUNCE_SEC", 60)
	if err != nil {
		return nil, err
	}

	// --- Access Control ---
	cfg.AccessControlEnabled = getEnv("ACCESS_CONTROL_ENABLED", "1") == "1"
	cfg.GeoBlockEnabled = getEnv("GEO_BLOCK_ENABLED", "1") == "1"

	cfg.MaxActiveApplicants, err = envInt("MAX_ACTIVE_APPLICANTS", 300)
	if err != nil {
		return nil, err
	}
	cfg.AccessSlotTTLSec, err = envInt("ACCESS_SLOT_TTL_SEC", 90)
	if err != nil {
		return nil, err
	}

	allowedStr := getEnv("ALLOWED_COUNTRY_CODES", "PK")
	for _, code := range strings.Split(allowedStr, ",") {
		clean := strings.TrimSpace(strings.ToUpper(code))
		if clean != "" {
			cfg.AllowedCountryCodes[clean] = true
		}
	}

	// --- Cache ---
	cfg.CacheEnabled = getEnv("CACHE_ENABLED", "1") == "1"
	cfg.CachePrefix = getEnv("CACHE_PREFIX", "peace_sme")

	cfg.CacheTTLUpdates, err = envInt("CACHE_TTL_UPDATES", 3600)
	if err != nil {
		return nil, err
	}
	cfg.CacheTTLFAQs, err = envInt("CACHE_TTL_FAQS", 300)
	if err != nil {
		return nil, err
	}
	cfg.CacheTTLFilters, err = envInt("CACHE_TTL_FILTERS", 120)
	if err != nil {
		return nil, err
	}

	return cfg, nil
}

// FindAdmin returns the admin user with the given username, or false if not found.
func (c *Config) FindAdmin(username string) (*AdminUser, bool) {
	for i := range c.AdminUsers {
		if c.AdminUsers[i].Username == username {
			return &c.AdminUsers[i], true
		}
	}
	return nil, false
}

// helpers

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func envInt(key string, defaultVal int) (int, error) {
	s := os.Getenv(key)
	if s == "" {
		return defaultVal, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("env var %s=%q is not a valid integer: %w", key, s, err)
	}
	return n, nil
}
