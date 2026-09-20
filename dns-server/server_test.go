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

func TestMakeResponseUnsupportedClass(t *testing.T) {
	query := dnsQuery("app.local", typeA)
	binary.BigEndian.PutUint16(query[len(query)-2:], 3)
	response := makeResponse(query)
	if response == nil {
		t.Fatal("expected a DNS response")
	}
	if got := binary.BigEndian.Uint16(response[2:4]); got != 0x8104 {
		t.Fatalf("flags = %#04x, want NOTIMP without authoritative answer", got)
	}
	if got := binary.BigEndian.Uint16(response[6:8]); got != 0 {
		t.Fatalf("answer count = %d, want 0", got)
	}
	if !bytes.Equal(response[headerSize:], query[headerSize:]) {
		t.Fatal("response did not preserve the question")
	}
}

func TestMakeResponseUnsupportedOpcode(t *testing.T) {
	query := dnsQuery("app.local", typeA)
	binary.BigEndian.PutUint16(query[2:4], 0x1100) // Opcode 2, recursion requested.
	response := makeResponse(query[:headerSize])
	if response == nil {
		t.Fatal("expected a DNS response")
	}
	if got := binary.BigEndian.Uint16(response[2:4]); got != 0x9104 {
		t.Fatalf("flags = %#04x, want opcode and NOTIMP", got)
	}
	if got := binary.BigEndian.Uint16(response[4:6]); got != 0 {
		t.Fatalf("question count = %d, want 0", got)
	}
	if len(response) != headerSize || !bytes.Equal(response[:2], query[:2]) {
		t.Fatal("expected header-only response with original transaction ID")
	}
}

func TestMakeResponseHandlesInvalidPackets(t *testing.T) {
	validQuery := dnsQuery("app.local", typeA)
	zeroQuestions := append([]byte(nil), validQuery...)
	binary.BigEndian.PutUint16(zeroQuestions[4:6], 0)
	twoQuestions := append([]byte(nil), validQuery...)
	binary.BigEndian.PutUint16(twoQuestions[4:6], 2)
	responsePacket := append([]byte(nil), validQuery...)
	responsePacket[2] |= 0x80
	compressedName := append([]byte(nil), validQuery...)
	compressedName[headerSize] = 0xc0
	longLabel := append([]byte(nil), validQuery...)
	longLabel[headerSize] = 20

	cases := []struct {
		name            string
		query           []byte
		wantFormatError bool
	}{
		{name: "short header", query: []byte{0, 1}},
		{name: "zero questions", query: zeroQuestions},
		{name: "response packet", query: responsePacket},
		{name: "multiple questions", query: twoQuestions, wantFormatError: true},
		{name: "compressed name", query: compressedName, wantFormatError: true},
		{name: "label exceeds packet", query: longLabel, wantFormatError: true},
		{name: "missing name terminator", query: validQuery[:headerSize+10], wantFormatError: true},
		{name: "truncated question", query: validQuery[:len(validQuery)-1], wantFormatError: true},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			response := makeResponse(testCase.query)
			if !testCase.wantFormatError {
				if response != nil {
					t.Fatal("expected packet to be ignored")
				}
				return
			}
			if len(response) != headerSize {
				t.Fatalf("response length = %d, want DNS header", len(response))
			}
			if got := binary.BigEndian.Uint16(response[2:4]); got != 0x8101 {
				t.Fatalf("flags = %#04x, want FORMERR", got)
			}
			if !bytes.Equal(response[:2], testCase.query[:2]) {
				t.Fatal("response did not preserve the transaction ID")
			}
		})
	}
}

func TestListenAddress(t *testing.T) {
	cases := []struct {
		name      string
		host      string
		port      int
		want      string
		wantError bool
	}{
		{name: "loopback", host: "127.0.0.1", port: 8053, want: "127.0.0.1:8053"},
		{name: "wildcard", host: "0.0.0.0", port: 8053, want: "0.0.0.0:8053"},
		{name: "empty host", host: "", port: 8053, want: ":8053"},
		{name: "port too low", host: "127.0.0.1", port: 0, wantError: true},
		{name: "port too high", host: "127.0.0.1", port: 65536, wantError: true},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			address, err := listenAddress(testCase.host, testCase.port)
			if testCase.wantError {
				if err == nil {
					t.Fatal("expected invalid address configuration to fail")
				}
				return
			}
			if err != nil {
				t.Fatalf("listenAddress() error = %v", err)
			}
			if address != testCase.want {
				t.Fatalf("listenAddress() = %q, want %q", address, testCase.want)
			}
		})
	}
}
