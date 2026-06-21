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
	Port                  int
	DatabaseURL           string
	RedisURL              string
	JWTSecret             string
	GrantApplicationOpen  bool
	GrantRequireSelection bool
	HFCShadowMode         bool
	CachePrefix           string
	AllowedCountryCodes   map[string]bool
	AdminUsers            []AdminUser
}

// AdminUser matches the schema of ADMIN_USERS_JSON configuration values.
type AdminUser struct {
	Username         string `json:"username"`
	PasswordHash     string `json:"password_hash"`
	Role             string `json:"role"`
	CanApproveGrants bool   `json:"can_approve_grants"`
}

func load() (*Config, error) {
	cfg := &Config{
		AllowedCountryCodes: make(map[string]bool),
	}
	portStr := getEnv("PORT", "8080")
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, fmt.Errorf("Parsing PORT %q failed: %v", portStr, err)
	}
	cfg.Port = port

	dbHost := getEnv("POSTGRES_HOST", "localhost")
	dbPort := getEnv("POSTGRES_PORT", "5432")
	dbUser := getEnv("POSTGRES_USER", "sme_user")
	dbPass := getEnv("POSTGRES_PASSWORD", "sme_password")
	dbName := getEnv("POSTGRES_DB", "sme_app")

	cfg.DatabaseURL = fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable", dbUser, dbPass, dbHost, dbPort, dbName)
	cfg.RedisURL = getEnv("REDIS_URL", "redis://localhost:6379/0")
	cfg.JWTSecret = os.Getenv("JWT_SECRET_KEY")
	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("required Environment Variable JWT_SECRET_KEY is not set")
	}
	cfg.GrantApplicationOpen = getEnv("GRANT_APPLICATION_OPEN", "0") == "1"
	cfg.GrantRequireSelection = getEnv("GRANT_REQUIRE_SELECTION", "1") == "1"
	cfg.HFCShadowMode = getEnv("HFC_SHADOW_MODE", "1") == "1"

	// 6. Split allowed country codes into a lookup map
	allowedStr := getEnv("ALLOWED_COUNTRY_CODES", "PK")
	for _, code := range strings.Split(allowedStr, ",") {
		clean := strings.TrimSpace(strings.ToUpper(code))
		if clean != "" {
			cfg.AllowedCountryCodes[clean] = true
		}
	}

	// 7. Unmarshal admin users array
	adminJSON := os.Getenv("ADMIN_USERS_JSON")
	if adminJSON != "" {
		var admins []AdminUser
		if err := json.Unmarshal([]byte(adminJSON), &admins); err != nil {
			return nil, fmt.Errorf("decoding ADMIN_USERS_JSON failed: %w", err)
		}
		cfg.AdminUsers = admins
	}

	return cfg, nil
}

func getEnv(key, defaultVal string) string {
	val := os.Getenv(key)
	if val == "" {
		return defaultVal
	}
	return val
}
