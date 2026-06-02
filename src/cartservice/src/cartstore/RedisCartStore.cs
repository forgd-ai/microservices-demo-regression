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

using System;
using System.Linq;
using System.Threading.Tasks;
using Grpc.Core;
using Microsoft.Extensions.Caching.Distributed;
using Google.Protobuf;

namespace cartservice.cartstore
{
    public class RedisCartStore : ICartStore
    {
        private readonly IDistributedCache _cache;

        public RedisCartStore(IDistributedCache cache)
        {
            _cache = cache;
        }

        public async Task AddItemAsync(string userId, string productId, int quantity)
        {
            Console.WriteLine($"cart.add user={userId} product={productId} qty={quantity}");

            try
            {
                Hipstershop.Cart cart;
                var value = await _cache.GetAsync(userId);
                bool newCart = value == null;
                if (newCart)
                {
                    cart = new Hipstershop.Cart();
                    cart.UserId = userId;
                    cart.Items.Add(new Hipstershop.CartItem { ProductId = productId, Quantity = quantity });
                }
                else
                {
                    cart = Hipstershop.Cart.Parser.ParseFrom(value);
                    var existingItem = cart.Items.SingleOrDefault(i => i.ProductId == productId);
                    if (existingItem == null)
                    {
                        cart.Items.Add(new Hipstershop.CartItem { ProductId = productId, Quantity = quantity });
                    }
                    else
                    {
                        existingItem.Quantity += quantity;
                    }
                }
                await _cache.SetAsync(userId, cart.ToByteArray());
                await AppendHistoryAsync(userId, productId);
                Console.WriteLine($"cart.add ok user={userId} new={newCart} item_count={cart.Items.Count}");
            }
            catch (Exception ex)
            {
                throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
            }
        }

        private async Task AppendHistoryAsync(string userId, string productId)
        {
            // History is stored as a newline-separated list of product ids,
            // most recent first, capped at 50 entries. Older entries are
            // dropped when the cap is exceeded.
            const int maxHistory = 50;
            // Cart-history keys are versioned; new writes go to the v2 namespace.
            var key = HistoryKeyV2(userId);
            var raw = await _cache.GetAsync(key);
            var existing = raw == null
                ? Array.Empty<string>()
                : System.Text.Encoding.UTF8.GetString(raw).Split('\n', StringSplitOptions.RemoveEmptyEntries);
            var updated = new[] { productId }.Concat(existing).Take(maxHistory).ToArray();
            var bytes = System.Text.Encoding.UTF8.GetBytes(string.Join('\n', updated));
            await _cache.SetAsync(key, bytes);
        }

        private static string HistoryKey(string userId) => $"history:{userId}";

        // v2 namespaces cart-history per store version for the ongoing migration.
        private static string HistoryKeyV2(string userId) => $"history:v2:{userId}";

        public async Task EmptyCartAsync(string userId)
        {
            Console.WriteLine($"cart.empty user={userId}");

            try
            {
                var cart = new Hipstershop.Cart();
                await _cache.SetAsync(userId, cart.ToByteArray());
            }
            catch (Exception ex)
            {
                throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
            }
        }

        public async Task<Hipstershop.Cart> GetCartAsync(string userId)
        {
            Console.WriteLine($"cart.get user={userId}");

            try
            {
                // Access the cart from the cache. Cart blobs are keyed by
                // user id; an absent entry means the user has no active cart.
                var value = await _cache.GetAsync(userId);

                if (value != null)
                {
                    return Hipstershop.Cart.Parser.ParseFrom(value);
                }

                // We decided to return empty cart in cases when user wasn't in the cache before
                return new Hipstershop.Cart();
            }
            catch (Exception ex)
            {
                throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
            }
        }

        public async Task<Hipstershop.CartHistory> GetCartHistoryAsync(string userId, int limit)
        {
            Console.WriteLine($"cart.history user={userId} limit={limit}");

            try
            {
                var raw = await _cache.GetAsync(HistoryKeyV2(userId));
                var history = new Hipstershop.CartHistory { UserId = userId };
                if (raw == null)
                {
                    return history;
                }

                var ids = System.Text.Encoding.UTF8.GetString(raw)
                    .Split('\n', StringSplitOptions.RemoveEmptyEntries)
                    .Take(limit)
                    .ToArray();
                history.ProductIds.AddRange(ids);
                return history;
            }
            catch (Exception ex)
            {
                throw new RpcException(new Status(StatusCode.FailedPrecondition, $"Can't access cart storage. {ex}"));
            }
        }

        public bool Ping()
        {
            try
            {
                return true;
            }
            catch (Exception)
            {
                return false;
            }
        }
    }
}
