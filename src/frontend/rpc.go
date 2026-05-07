// Copyright 2018 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/frontend/genproto"

	"github.com/pkg/errors"
)

const (
	avoidNoopCurrencyConversionRPC = false
)

func (fe *frontendServer) getCurrencies(ctx context.Context) ([]string, error) {
	currs, err := pb.NewCurrencyServiceClient(fe.currencySvcConn).
		GetSupportedCurrencies(ctx, &pb.Empty{})
	if err != nil {
		return nil, err
	}
	var out []string
	for _, c := range currs.CurrencyCodes {
		if _, ok := whitelistedCurrencies[c]; ok {
			out = append(out, c)
		}
	}
	return out, nil
}

func (fe *frontendServer) getProducts(ctx context.Context) ([]*pb.Product, error) {
	resp, err := pb.NewProductCatalogServiceClient(fe.productCatalogSvcConn).
		ListProducts(ctx, &pb.Empty{})
	return resp.GetProducts(), err
}

func (fe *frontendServer) getProduct(ctx context.Context, id string) (*pb.Product, error) {
	resp, err := pb.NewProductCatalogServiceClient(fe.productCatalogSvcConn).
		GetProduct(ctx, &pb.GetProductRequest{Id: id})
	return resp, err
}

func (fe *frontendServer) getCart(ctx context.Context, userID string) ([]*pb.CartItem, error) {
	resp, err := pb.NewCartServiceClient(fe.cartSvcConn).GetCart(ctx, &pb.GetCartRequest{UserId: userID})
	return resp.GetItems(), err
}

func (fe *frontendServer) emptyCart(ctx context.Context, userID string) error {
	_, err := pb.NewCartServiceClient(fe.cartSvcConn).EmptyCart(ctx, &pb.EmptyCartRequest{UserId: userID})
	return err
}

func (fe *frontendServer) insertCart(ctx context.Context, userID, productID string, quantity int32) error {
	_, err := pb.NewCartServiceClient(fe.cartSvcConn).AddItem(ctx, &pb.AddItemRequest{
		UserId: userID,
		Item: &pb.CartItem{
			ProductId: productID,
			Quantity:  quantity},
	})
	return err
}

func (fe *frontendServer) convertCurrency(ctx context.Context, money *pb.Money, currency string) (*pb.Money, error) {
	if avoidNoopCurrencyConversionRPC && money.GetCurrencyCode() == currency {
		return money, nil
	}
	return pb.NewCurrencyServiceClient(fe.currencySvcConn).
		Convert(ctx, &pb.CurrencyConversionRequest{
			From:   money,
			ToCode: currency})
}

func (fe *frontendServer) getShippingQuote(ctx context.Context, items []*pb.CartItem, currency string) (*pb.Money, error) {
	quote, err := pb.NewShippingServiceClient(fe.shippingSvcConn).GetQuote(ctx,
		&pb.GetQuoteRequest{
			Address: nil,
			Items:   items})
	if err != nil {
		return nil, err
	}
	localized, err := fe.convertCurrency(ctx, quote.GetCostUsd(), currency)
	return localized, errors.Wrap(err, "failed to convert currency for shipping cost")
}

func (fe *frontendServer) getRecommendations(ctx context.Context, userID string, productIDs []string) ([]*pb.Product, error) {
	resp, err := pb.NewRecommendationServiceClient(fe.recommendationSvcConn).ListRecommendations(ctx,
		&pb.ListRecommendationsRequest{UserId: userID, ProductIds: productIDs})
	if err != nil {
		return nil, err
	}
	out := make([]*pb.Product, len(resp.GetProductIds()))
	for i, v := range resp.GetProductIds() {
		p, err := fe.getProduct(ctx, v)
		if err != nil {
			return nil, errors.Wrapf(err, "failed to get recommended product info (#%s)", v)
		}
		out[i] = p
	}
	if len(out) > 4 {
		out = out[:4] // take only first four to fit the UI
	}
	return out, err
}

type fbtView struct {
	Item   *pb.Product
	Reason string
	Count  int32
}

// fbtCallKey returns a stable key for an FBT request so concurrent
// callers with identical inputs can share an upstream call.
func fbtCallKey(userID string, productIDs []string) string {
	ids := make([]string, len(productIDs))
	copy(ids, productIDs)
	sort.Strings(ids)
	return userID + "|" + strings.Join(ids, ",")
}

type fbtInFlight struct {
	done   chan struct{}
	result []fbtView
	err    error
}

var (
	fbtInFlightMu     sync.Mutex
	fbtInFlightCalls  = make(map[string]*fbtInFlight)
)

// getFrequentlyBoughtTogether coalesces duplicate concurrent FBT
// requests with the same user and cart contents. Rapid navigation —
// back-button, the checkout flow, double-clicking through the cart
// page — can fire the same FBT call several times in quick succession;
// this collapses them into a single upstream request and shares the
// result across all waiters.
func (fe *frontendServer) getFrequentlyBoughtTogether(ctx context.Context, userID string, productIDs []string) ([]fbtView, error) {
	key := fbtCallKey(userID, productIDs)

	fbtInFlightMu.Lock()
	if existing, ok := fbtInFlightCalls[key]; ok {
		fbtInFlightMu.Unlock()
		select {
		case <-existing.done:
			return existing.result, existing.err
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	pending := &fbtInFlight{done: make(chan struct{})}
	fbtInFlightCalls[key] = pending
	fbtInFlightMu.Unlock()

	defer func() {
		fbtInFlightMu.Lock()
		delete(fbtInFlightCalls, key)
		fbtInFlightMu.Unlock()
		close(pending.done)
	}()

	resp, err := pb.NewRecommendationServiceClient(fe.recommendationSvcConn).ListFrequentlyBoughtTogether(ctx,
		&pb.FBTRequest{UserId: userID, ProductIds: productIDs, MaxResults: 4})
	if err != nil {
		pending.err = err
		return nil, err
	}
	out := make([]fbtView, 0, len(resp.GetItems()))
	for _, item := range resp.GetItems() {
		p, err := fe.getProduct(ctx, item.GetProductId())
		if err != nil {
			pending.err = errors.Wrapf(err, "failed to get FBT product info (#%s)", item.GetProductId())
			return nil, pending.err
		}
		out = append(out, fbtView{
			Item:   p,
			Reason: item.GetReason(),
			Count:  item.GetCooccurrenceCount(),
		})
	}
	pending.result = out
	return out, nil
}

func (fe *frontendServer) getAd(ctx context.Context, ctxKeys []string) ([]*pb.Ad, error) {
	ctx, cancel := context.WithTimeout(ctx, time.Millisecond*100)
	defer cancel()

	resp, err := pb.NewAdServiceClient(fe.adSvcConn).GetAds(ctx, &pb.AdRequest{
		ContextKeys: ctxKeys,
	})
	return resp.GetAds(), errors.Wrap(err, "failed to get ads")
}
