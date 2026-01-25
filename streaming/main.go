package main

import (
	"encoding/json" // New import for sending JSON over WebSocket
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins for now
	},
}

const csvFilePath = "/app/static_data/questdb-query-1769038517286.csv" // Define CSV file path
var historicalCandles []Candle // To store loaded candles

// WSTick represents a single price update for the frontend
type WSTick struct {
	Timestamp    time.Time `json:"timestamp"`
	InstrumentID int       `json:"instrumentId"`
	Open         float64   `json:"open"`
	High         float64   `json:"high"`
	Low          float64   `json:"low"`
	Close        float64   `json:"close"` // This will be the current interpolated price
	Volume       int       `json:"volume"`
	IsFinal      bool      `json:"isFinal"` // Indicates if this is the final tick for the candle
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("Failed to upgrade to websocket: %v\n", err)
		return
	}
	defer conn.Close()
	log.Println("WebSocket client connected.")

	// Stream historical candles
	for i, candle := range historicalCandles {
		log.Printf("Streaming candle %d for InstrumentID %d\n", i, candle.InstrumentID)
		// Simulate 5 minutes (300 seconds) of ticks
		for tick := 0; tick < 150; tick++ { // 300 seconds / 2 seconds per tick = 150 ticks
			time.Sleep(2 * time.Second)

			// Simple linear interpolation for price
			// Current price will move from Open to Close over 149 intervals (150 ticks)
			interpolatedClose := candle.Open + (candle.Close-candle.Open)*float64(tick)/149

			// Determine current high/low for the forming candle based on interpolated price
			currentHigh := candle.Open
			if interpolatedClose > currentHigh {
				currentHigh = interpolatedClose
			}
			currentLow := candle.Open
			if interpolatedClose < currentLow {
				currentLow = interpolatedClose
			}
			// Also ensure that the current high/low at least includes the actual high/low
			// This is a simplification; a more accurate simulation might involve random walks
			if candle.High > currentHigh {
				currentHigh = candle.High
			}
			if candle.Low < currentLow {
				currentLow = candle.Low
			}


			isFinal := (tick == 149)

			tickData := WSTick{
				Timestamp:    candle.Timestamp,
				InstrumentID: candle.InstrumentID,
				Open:         candle.Open,
				High:         currentHigh, // Simplified
				Low:          currentLow,  // Simplified
				Close:        interpolatedClose,
				Volume:       candle.Volume, // Volume for the entire candle
				IsFinal:      isFinal,
			}

			jsonTick, err := json.Marshal(tickData)
			if err != nil {
				log.Printf("Error marshalling tick data: %v\n", err)
				continue
			}

			if err := conn.WriteMessage(websocket.TextMessage, jsonTick); err != nil {
				log.Printf("Error writing message: %v\n", err)
				return // Client disconnected
			}
		}
	}

	log.Println("Finished streaming all historical data.")
	// Block forever to keep the goroutine alive if no further data
	select {}
}

func main() {
	// Load historical candles from CSV
	var err error
	historicalCandles, err = ReadCandlesFromCSV(csvFilePath)
	if err != nil {
		log.Fatalf("Error reading historical candles from CSV: %v\n", err)
	}
	log.Printf("Loaded %d historical candles from %s\n", len(historicalCandles), csvFilePath)


	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "Go Streaming Server (HTTP) is running.")
	})

	http.HandleFunc("/ws", wsHandler) // New WebSocket endpoint

	log.Println("Starting Go streaming server on :8082")
	if err := http.ListenAndServe(":8082", nil); err != nil {
		log.Fatalf("could not start server: %s\n", err)
	}
}
