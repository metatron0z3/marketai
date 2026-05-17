package main

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"log"
	"time"
)

// Candle represents a single 5-minute candlestick data point
type Candle struct {
	Timestamp    time.Time
	InstrumentID int
	Open         float64
	High         float64
	Low          float64
	Close        float64
	Volume       int
}

// ReadCandlesFromCSV reads candlestick data from a CSV file
func ReadCandlesFromCSV(filePath string) ([]Candle, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("unable to open CSV file: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	// Read the header row
	_, err = reader.Read()
	if err == io.EOF {
		return nil, fmt.Errorf("CSV file is empty")
	}
	if err != nil {
		return nil, fmt.Errorf("unable to read CSV header: %w", err)
	}

	var candles []Candle
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("unable to read CSV record: %w", err)
		}

		// Parse timestamp
		// Example: "2024-01-02T23:50:00.000000Z"
		t, err := time.Parse("2006-01-02T15:04:05.000000Z", record[0])
		if err != nil {
			log.Printf("Failed to parse timestamp %q: %v\n", record[0], err)
			continue
		}

		instrumentID, err := strconv.Atoi(record[1])
		if err != nil {
			log.Printf("Failed to parse InstrumentID %q: %v\n", record[1], err)
			continue
		}

		open, err := strconv.ParseFloat(record[2], 64)
		if err != nil {
			log.Printf("Failed to parse Open %q: %v\n", record[2], err)
			continue
		}

		high, err := strconv.ParseFloat(record[3], 64)
		if err != nil {
			log.Printf("Failed to parse High %q: %v\n", record[3], err)
			continue
		}

		low, err := strconv.ParseFloat(record[4], 64)
		if err != nil {
			log.Printf("Failed to parse Low %q: %v\n", record[4], err)
			continue
		}

		closeVal, err := strconv.ParseFloat(record[5], 64)
		if err != nil {
			log.Printf("Failed to parse Close %q: %v\n", record[5], err)
			continue
		}

		volume, err := strconv.Atoi(record[6])
		if err != nil {
			log.Printf("Failed to parse Volume %q: %v\n", record[6], err)
			continue
		}

		candles = append(candles, Candle{
			Timestamp:    t,
			InstrumentID: instrumentID,
			Open:         open,
			High:         high,
			Low:          low,
			Close:        closeVal,
			Volume:       volume,
		})
	}

	// Sort candles chronologically (oldest first) - required by lightweight-charts
	sort.Slice(candles, func(i, j int) bool {
		return candles[i].Timestamp.Before(candles[j].Timestamp)
	})

	return candles, nil
}
