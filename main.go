package main

import (
	"log"
	"peace-sme-go/internal/config"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Startup failed: %v", err)
	}
	log.Printf("Configuration loaded successfully.")
	log.Printf("  Server port:          %d", cfg.Port)
	log.Printf("  Grant registration:   %v", boolLabel(cfg.GrantApplicationOpen, "OPEN", "CLOSED"))
	log.Printf("  Grant require select: %v", boolLabel(cfg.GrantRequireSelection, "YES", "NO"))
	log.Printf("  HFC shadow mode:      %v", boolLabel(cfg.HFCShadowMode, "ON (non-blocking)", "OFF (blocking)"))
	log.Printf("  Geo blocking:         %v", boolLabel(cfg.GeoBlockEnabled, "ON", "OFF"))
	log.Printf("  Admin users loaded:   %d", len(cfg.AdminUsers))
	log.Printf("  Cache prefix:         %s", cfg.CachePrefix)
	log.Printf("  Allowed countries:    %v", keysOf(cfg.AllowedCountryCodes))
}

func keysOf(m map[string]bool) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}

func boolLabel(b bool, ifTrue, ifFalse string) string {
	if b {
		return ifTrue
	}
	return ifFalse
}
