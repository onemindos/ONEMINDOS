// SPDX-License-Identifier: Apache-2.0

package onemind

import (
	"context"
	"net/http"
	"net/url"
)

// DomainHost is one name an owner asked for under their own domain (<app>.<domain>). State "approved"
// records a decision only: nothing is served from the name yet.
type DomainHost struct {
	Hostname    string  `json:"hostname"`
	AppID       string  `json:"app_id"`
	State       string  `json:"state"`
	RequestedBy *string `json:"requested_by"`
	ApprovedBy  *string `json:"approved_by"`
	UpdatedAt   *string `json:"updated_at"`
	Public      bool    `json:"public"`
}

// DomainProof is the DNS record that proves the owner controls the domain.
type DomainProof struct {
	Type  string `json:"type"`
	Name  string `json:"name"`
	Value string `json:"value"`
}

// Domain is a registered domain with its proof record and the names asked for under it.
type Domain struct {
	Domain     string       `json:"domain"`
	Verified   bool         `json:"verified"`
	VerifiedAt *string      `json:"verified_at"`
	Proof      DomainProof  `json:"proof"`
	Hosts      []DomainHost `json:"hosts"`
}

// DomainsSummary is GET /v1/domains. Enabled is false until the owner turns bring-your-own-domain on
// for the box; adding then answers 409 domains_disabled.
type DomainsSummary struct {
	Enabled bool `json:"enabled"`
	ACME    struct {
		AccountThumbprint *string `json:"account_thumbprint"`
		Issuance          string  `json:"issuance"`
	} `json:"acme"`
	Domains []Domain `json:"domains"`
}

// DomainsService is /v1/domains (NET-DOM-01, #238), owner only.
type DomainsService struct{ c *Client }

// List is operation domains.list.
func (s *DomainsService) List(ctx context.Context) (*DomainsSummary, error) {
	var v DomainsSummary
	return &v, s.c.Do(ctx, http.MethodGet, "/v1/domains", nil, &v)
}

// Add is operation domains.add: registers the domain and returns the TXT record to add at the DNS provider.
func (s *DomainsService) Add(ctx context.Context, domain string) (*Domain, error) {
	var v Domain
	return &v, s.c.Do(ctx, http.MethodPost, "/v1/domains", map[string]string{"domain": domain}, &v)
}

// RequestHost is operation domains.host_request: ask for <app>.<domain>. It waits for the owner to approve it.
func (s *DomainsService) RequestHost(ctx context.Context, domain, appID string) (*DomainHost, error) {
	var v DomainHost
	return &v, s.c.Do(ctx, http.MethodPost, "/v1/domains/"+url.PathEscape(domain)+"/hosts", map[string]string{"app_id": appID}, &v)
}

// ApproveHost is operation domains.host_approve. confirm must be the hostname typed in full; approving
// records a decision only, nothing is served yet.
func (s *DomainsService) ApproveHost(ctx context.Context, hostname, confirm string) (*DomainHost, error) {
	var v DomainHost
	return &v, s.c.Do(ctx, http.MethodPost, "/v1/domains/hosts/"+url.PathEscape(hostname)+"/approve", map[string]string{"confirm": confirm}, &v)
}

// RemoveHost is operation domains.host_remove: withdraw a requested or approved name.
func (s *DomainsService) RemoveHost(ctx context.Context, hostname string) error {
	return s.c.Do(ctx, http.MethodDelete, "/v1/domains/hosts/"+url.PathEscape(hostname), nil, nil)
}
