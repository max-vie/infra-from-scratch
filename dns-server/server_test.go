package main

import (
	"bytes"
	"encoding/binary"
	"strings"
	"testing"
)

// Build a minimal DNS query for the response tests.
func dnsQuery(name string, queryType uint16) []byte {
	// DNS names are encoded as length-prefixed labels, not plain text.
	labels := []byte{}
	for _, label := range strings.Split(name, ".") {
		labels = append(labels, byte(len(label)))
		labels = append(labels, []byte(label)...)
	}
	labels = append(labels, 0) // Zero marks the end of the DNS name.

	// Allocate space for the header, encoded name, type, and class.
	query := make([]byte, headerSize+len(labels)+4)
	binary.BigEndian.PutUint16(query[0:2], 0x1234) // Transaction ID.
	binary.BigEndian.PutUint16(query[2:4], 0x0100) // Query with recursion requested.
	binary.BigEndian.PutUint16(query[4:6], 1)      // One question.
	copy(query[headerSize:], labels)

	questionEnd := headerSize + len(labels)
	// The question ends with its record type and DNS class.
	binary.BigEndian.PutUint16(query[questionEnd:questionEnd+2], queryType)
	binary.BigEndian.PutUint16(query[questionEnd+2:questionEnd+4], classIN)
	return query
}

func TestMakeResponseKnownARecord(t *testing.T) {
	// A known A query should return the configured address.
	response := makeResponse(dnsQuery("app.local", typeA))
	if response == nil {
		t.Fatal("expected a DNS response")
	}

	// Header bytes 6-7 contain the number of answers.
	if got := binary.BigEndian.Uint16(response[6:8]); got != 1 {
		t.Fatalf("answer count = %d, want 1", got)
	}
	// The final four bytes contain the IPv4 address 127.0.0.1.
	if !bytes.Equal(response[len(response)-4:], []byte{127, 0, 0, 1}) {
		t.Fatalf("address = %v, want 127.0.0.1", response[len(response)-4:])
	}
}

func TestMakeResponseUnknownName(t *testing.T) {
	// An unknown name should return NXDOMAIN with no answer.
	response := makeResponse(dnsQuery("unknown.local", typeA))
	if response == nil {
		t.Fatal("expected a DNS response")
	}

	// The lower four flag bits contain the response code: 3 means NXDOMAIN.
	if got := binary.BigEndian.Uint16(response[2:4]) & 0x000f; got != 3 {
		t.Fatalf("response code = %d, want NXDOMAIN", got)
	}
	if got := binary.BigEndian.Uint16(response[6:8]); got != 0 {
		t.Fatalf("answer count = %d, want 0", got)
	}
}

func TestMakeResponseUnsupportedType(t *testing.T) {
	// A known name with an unsupported type should return no answer.
	response := makeResponse(dnsQuery("app.local", 28))
	if response == nil {
		t.Fatal("expected a DNS response")
	}

	// An unsupported type is a valid response with response code 0 and no answer.
	if got := binary.BigEndian.Uint16(response[2:4]) & 0x000f; got != 0 {
		t.Fatalf("response code = %d, want 0", got)
	}
	if got := binary.BigEndian.Uint16(response[6:8]); got != 0 {
		t.Fatalf("answer count = %d, want 0", got)
	}
}

func TestMakeResponseRejectsMalformedQuery(t *testing.T) {
	// A packet shorter than a DNS header should be ignored.
	if response := makeResponse([]byte{0, 1}); response != nil {
		t.Fatal("expected malformed query to be rejected")
	}
}
