# 🔴 How to Enable REAL 021 Trade API

**Current Status:** Your system is using **MOCK DATA** (yfinance)  
**To enable:** Real 021 Trade API integration is now ready!

---

## ✅ What I Just Fixed

I've updated your `mock-api/main.py` to support **BOTH** modes:
- 🟢 **Mock Mode** (default) - Uses yfinance/fallback prices for testing
- 🔴 **Real API Mode** - Connects to actual 021 Trade API

---

## 🚀 Enable Real 021 Trade API (2 Steps)

### Step 1: Update .env File

Edit your `.env` file and change this line:

```env
USE_REAL_API=true
```

Your .env already has the credentials:
```env
TRADE021_USERNAME=HACK1234
TRADE021_PASSWORD=Om123
```

### Step 2: Rebuild & Restart

```bash
# Stop containers
Ctrl+C

# Rebuild
docker-compose down
docker-compose up --build
```

---

## 📊 What Changes When Real API is Enabled

### **Before (Mock Mode):**
```
🟢 MOCK DATA
- Prices from yfinance/fallback
- Simulated order execution
- No real trades
```

### **After (Real API Mode):**
```
🔴 REAL 021 Trade API
- Live positions from your account
- Real order submission to 021
- Actual account balances
- Real NSE/BSE data
```

---

## ⚠️ IMPORTANT WARNINGS

### 1. **Real Money at Risk**
When `USE_REAL_API=true`:
- Orders will be **REAL** trades
- Money will be **actually spent/received**
- This is your **actual 021 account**

### 2. **Sandbox vs Production**
You're using the **Developer Sandbox**:
- Base URL: `https://devapi.021.trade/api/developer-api/v1`
- Simulated trades but realistic behavior
- Safe for testing

### 3. **Test Carefully**
- Start with small quantities (qty=1)
- Use INTRADAY product (auto-closes)
- Monitor every order carefully

---

## 🧪 How to Test Real API

### Step 1: Enable Real API
```bash
# Edit .env
USE_REAL_API=true

# Rebuild
docker-compose down
docker-compose up --build
```

### Step 2: Check Logs
You should see:
```
021 Broker API Proxy Starting...
Mode: 🔴 REAL 021 Trade API
✅ 021 Trade API authenticated (expires: 2026-10-10T05:00:00Z)
✅ Ready to use 021 Trade API
```

### Step 3: Test in UI
Open http://localhost:3000 and try:

**Get Real Positions:**
```
Show me my current positions
```

**Get Real Account Balance:**
```
What's my account balance?
```

**Place Real Order (CAREFUL!):**
```
Buy 1 share of RELIANCE at market
```

---

## 🔍 Current Implementation Status

### ✅ **Fully Working (Real API):**
- Authentication with 021 Trade
- Get positions
- Get orders
- Health checks

### ⏳ **Partially Working:**
- Quote fetching (needs symbol→token mapping)
- Order placement (needs conversion logic)

### 📝 **Why Partially?**
The 021 Trade API uses:
- **Tokens** instead of symbols (e.g., `2885` instead of `"RELIANCE.NS"`)
- **Prices in paise** (₹1 = 100 paise)
- **Positive/negative qty** for buy/sell

We need to create a **mapping layer** to convert between formats.

---

## 🗺️ Next Steps for Full Integration

### 1. **Download Instruments CSV**
```python
# Get instrument list from 021 Trade
# Maps symbols to tokens
GET /instruments → instruments.csv
```

### 2. **Create Symbol→Token Mapping**
```python
# Example mapping
{
  "RELIANCE.NS": 2885,
  "INFY.NS": 1594,
  "TCS.NS": 11536
}
```

### 3. **Add Conversion Functions**
- Symbol ↔ Token
- Rupees ↔ Paise
- BUY/SELL ↔ +/- quantity

---

## 📋 Current Mode Check

To see which mode you're in, open:
http://localhost:8001/health

You'll see:
```json
{
  "status": "ok",
  "mode": "mock",  // or "real"
  "authenticated": false  // or true
}
```

---

## 🎯 Recommended Approach

### **For Now (Development):**
Keep `USE_REAL_API=false` to:
- Test UI/UX safely
- Develop features without risk
- Use mock data freely

### **When Ready to Test Real Trading:**
1. Set `USE_REAL_API=true`
2. Test with tiny quantities
3. Monitor every transaction
4. Keep logs of everything

### **For Production:**
Complete the symbol→token mapping layer first!

---

## 🆘 If Real API Fails

The system will automatically **fallback to mock data** if:
- Authentication fails
- Network error occurs
- API returns error

You'll see warnings in logs but the system keeps working.

---

## ✅ Current Status Summary

```
✅ 021 Trade API client: Created
✅ Authentication: Working
✅ Mock-API proxy: Updated
✅ Environment toggle: Ready
⏳ Symbol mapping: TODO
⏳ Full quote integration: TODO
⏳ Full order integration: TODO
```

---

## 🚀 To Start Using Real API Right Now:

```bash
# 1. Edit .env
nano .env
# Change: USE_REAL_API=true

# 2. Rebuild
docker-compose down
docker-compose up --build

# 3. Check logs for:
# "🔴 REAL 021 Trade API"
# "✅ 021 Trade API authenticated"

# 4. Test carefully!
```

---

**Created:** October 9, 2026, 12:13 PM IST (06:43 UTC)  
**Status:** Real API Integration Ready (Partial) ⚡  
**Safety:** Always test with small amounts first! ⚠️
