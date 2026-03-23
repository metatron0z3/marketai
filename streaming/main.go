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

	// Stream historical candles - one complete candle every 2 seconds
	for i, candle := range historicalCandles {
		if i%50 == 0 {
			log.Printf("Streaming candle %d/%d for InstrumentID %d\n", i, len(historicalCandles), candle.InstrumentID)
		}

		tickData := WSTick{
			Timestamp:    candle.Timestamp,
			InstrumentID: candle.InstrumentID,
			Open:         candle.Open,
			High:         candle.High,
			Low:          candle.Low,
			Close:        candle.Close,
			Volume:       candle.Volume,
			IsFinal:      true, // Each candle is complete
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

		time.Sleep(2 * time.Second) // New candle every 2 seconds
	}

	log.Println("Finished streaming all historical data.")
	// Keep connection open
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
