package config

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
