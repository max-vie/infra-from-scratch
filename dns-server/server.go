package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"net"
)

const (
	listenAddress = "127.0.0.1:8053"
	headerSize    = 12
	typeA         = 1
	classIN       = 1
)

var recordName = []byte("\x03app\x05local\x00")

func main() {
	// Bind a UDP socket for local DNS queries.
	server, err := net.ListenPacket("udp4", listenAddress)
	if err != nil {
		panic(err)
	}
	defer server.Close()

	fmt.Printf("serving DNS on %s ...\n", listenAddress)
	buffer := make([]byte, 512)

	for {
		// Wait for the next DNS query.
		size, client, err := server.ReadFrom(buffer)
		if err != nil {
			continue
		}

		response := makeResponse(buffer[:size])
		if response == nil {
			continue
		}
		_, _ = server.WriteTo(response, client)
	}
}

func makeResponse(query []byte) []byte {
	// A DNS header is 12 bytes; this MVP accepts one question.
	if len(query) < headerSize || binary.BigEndian.Uint16(query[4:6]) != 1 {
		return nil
	}

	queryFlags := binary.BigEndian.Uint16(query[2:4])
	if queryFlags&0x8000 != 0 {
		return nil
	}

	// Walk over the encoded labels to find the end of the name.
	position := headerSize
	for {
		if position >= len(query) {
			return nil
		}

		length := int(query[position])
		position++
		if length == 0 {
			break
		}
		if length&0xc0 != 0 || position+length > len(query) {
			return nil
		}
		position += length
	}

	if position+4 > len(query) {
		return nil
	}
	questionEnd := position + 4
	question := query[headerSize:questionEnd]
	queryType := binary.BigEndian.Uint16(query[position:])
	queryClass := binary.BigEndian.Uint16(query[position+2:])

	// Return the fixed A record or NXDOMAIN for an unknown name.
	flags := uint16(0x8400) | queryFlags&0x0100
	var answer []byte
	answerCount := uint16(0)
	if !bytes.EqualFold(query[headerSize:position], recordName) {
		flags = 0x8403 | queryFlags&0x0100
	} else if queryType == typeA && queryClass == classIN {
		answerCount = 1
		answer = []byte{
			0xc0, 0x0c, // Pointer to the name in the question.
			0x00, 0x01, // Type A.
			0x00, 0x01, // Class IN.
			0x00, 0x00, 0x00, 0x3c, // TTL: 60 seconds.
			0x00, 0x04, // IPv4 address length.
			0x7f, 0x00, 0x00, 0x01, // 127.0.0.1.
		}
	}

	// Reuse the transaction ID and original question in the response.
	response := make([]byte, headerSize+len(question)+len(answer))
	copy(response[0:2], query[0:2])
	binary.BigEndian.PutUint16(response[2:4], flags)
	binary.BigEndian.PutUint16(response[4:6], 1)
	binary.BigEndian.PutUint16(response[6:8], answerCount)
	copy(response[headerSize:], question)
	copy(response[headerSize+len(question):], answer)
	return response
}
