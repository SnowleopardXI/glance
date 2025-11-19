package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"gopkg.in/yaml.v3"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "yaml_to_json: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("read stdin: %w", err)
	}
	var node yaml.Node
	if err := yaml.Unmarshal(data, &node); err != nil {
		return fmt.Errorf("parse yaml: %w", err)
	}
	if len(node.Content) == 0 {
		return errors.New("empty document")
	}
	normalized := convertNode(node.Content[0])
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(normalized); err != nil {
		return fmt.Errorf("write json: %w", err)
	}
	return nil
}

type mapEntry struct {
	Key   string
	Value interface{}
}

type orderedMap struct {
	Entries []mapEntry
}

func (o orderedMap) MarshalJSON() ([]byte, error) {
	var buf bytes.Buffer
	buf.WriteByte('{')
	for i, entry := range o.Entries {
		if i > 0 {
			buf.WriteByte(',')
		}
		keyBytes, err := json.Marshal(entry.Key)
		if err != nil {
			return nil, err
		}
		buf.Write(keyBytes)
		buf.WriteByte(':')
		valBytes, err := json.Marshal(entry.Value)
		if err != nil {
			return nil, err
		}
		buf.Write(valBytes)
	}
	buf.WriteByte('}')
	return buf.Bytes(), nil
}

func convertNode(node *yaml.Node) interface{} {
	switch node.Kind {
	case yaml.MappingNode:
		entries := make([]mapEntry, 0, len(node.Content)/2)
		for i := 0; i < len(node.Content); i += 2 {
			keyNode := node.Content[i]
			valueNode := node.Content[i+1]
			entries = append(entries, mapEntry{Key: keyNode.Value, Value: convertNode(valueNode)})
		}
		return orderedMap{Entries: entries}
	case yaml.SequenceNode:
		items := make([]interface{}, len(node.Content))
		for i, child := range node.Content {
			items[i] = convertNode(child)
		}
		return items
	case yaml.ScalarNode:
		var out interface{}
		if err := node.Decode(&out); err == nil {
			return out
		}
		return node.Value
	case yaml.DocumentNode:
		if len(node.Content) > 0 {
			return convertNode(node.Content[0])
		}
		return nil
	default:
		return nil
	}
}
