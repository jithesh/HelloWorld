from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import RefreshError
import pandas as pd
import numpy as np
from emergentintegrations.llm.chat import LlmChat, UserMessage
import asyncio
import json
from urllib.parse import quote, unquote

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer(auto_error=False)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = "your-google-client-id"  # Will be configured via frontend OAuth
GOOGLE_CLIENT_SECRET = "your-google-client-secret"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly', 'openid', 'profile', 'email']

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    google_access_token: Optional[str] = None
    google_refresh_token: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str
    expires_at: datetime

class StockData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    price: float
    timestamp: datetime
    alert_id: str
    raw_data: Dict[str, Any]

class StockAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    current_price: float
    price_change: float
    percentage_change: float
    volume: Optional[int] = None
    analysis_type: str  # 'daily', 'weekly', 'monthly'
    ai_insights: Optional[str] = None
    trend: str  # 'bullish', 'bearish', 'neutral'
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DashboardSummary(BaseModel):
    total_stocks: int
    top_gainers: List[Dict[str, Any]]
    top_losers: List[Dict[str, Any]]
    best_performers: List[Dict[str, Any]]
    total_portfolio_change: float
    total_portfolio_percentage: float
    ai_market_insights: Optional[str] = None
    last_updated: datetime

# Helper Functions
def prepare_for_mongo(data):
    """Convert datetime objects to ISO strings for MongoDB storage"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
    return data

def parse_from_mongo(item):
    """Convert ISO strings back to datetime objects"""
    if isinstance(item, dict):
        for key, value in item.items():
            if isinstance(value, str) and 'T' in value:
                try:
                    item[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except:
                    pass
    return item

async def get_current_user(request: Request) -> Optional[User]:
    """Get current user from session token"""
    try:
        # Try cookie first
        session_token = request.cookies.get('session_token')
        
        # Fallback to Authorization header
        if not session_token:
            auth = await security(request)
            if auth:
                session_token = auth.credentials
        
        if not session_token:
            return None
            
        # Find user in database
        current_time = datetime.now(timezone.utc)
        user_data = await db.users.find_one({
            "session_token": session_token
        })
        
        # Check expiration
        if user_data:
            expires_at = user_data.get('expires_at')
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except:
                    expires_at = current_time  # Treat as expired if can't parse
            
            if expires_at <= current_time:
                # Session expired, delete it
                await db.users.delete_one({"session_token": session_token})
                return None
        
        if user_data:
            return User(**parse_from_mongo(user_data))
        return None
    except Exception:
        return None

async def fetch_google_sheet_data(sheet_id: str, range_name: str, access_token: str):
    """Fetch data from Google Sheets - specifically from Boom sheet"""
    try:
        credentials = Credentials(token=access_token)
        service = build('sheets', 'v4', credentials=credentials)
        
        # Fetch from Boom sheet (7th sheet) - adjust range if needed
        boom_sheet_range = "Boom!A:D"  # Boom sheet, columns A-D
        
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=boom_sheet_range
        ).execute()
        
        return result.get('values', [])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch Boom sheet data: {str(e)}")

def parse_stock_data(raw_data):
    """Parse the Boom sheet stock data - each row is one stock entry"""
    parsed_stocks = []
    
    for row in raw_data[1:]:  # Skip header
        if len(row) >= 4:
            stock_symbol = row[0].strip()
            price_str = row[1]
            timestamp_str = row[2]
            alert_msg = row[3]
            
            # Parse timestamp
            try:
                timestamp = datetime.strptime(timestamp_str, '%I:%M:%S %p').replace(
                    year=datetime.now().year,
                    month=datetime.now().month,
                    day=datetime.now().day,
                    tzinfo=timezone.utc
                )
            except:
                timestamp = datetime.now(timezone.utc)
            
            # Parse price
            try:
                price = float(price_str)
                parsed_stocks.append({
                    'symbol': stock_symbol,
                    'price': price,
                    'timestamp': timestamp,
                    'alert_id': alert_msg,
                    'raw_data': {
                        'original_row': row
                    }
                })
            except ValueError:
                continue
    
    return parsed_stocks

async def generate_ai_insights(stock_data, analysis_type="market_overview"):
    """Generate AI-powered insights using Emergent LLM"""
    try:
        # Initialize LLM chat
        chat = LlmChat(
            api_key=os.environ.get('EMERGENT_LLM_KEY'),
            session_id=f"stock_analysis_{datetime.now().timestamp()}",
            system_message="You are an expert financial analyst specializing in stock market analysis and investment recommendations."
        ).with_model("openai", "gpt-4o")
        
        # Prepare data summary for AI analysis
        if analysis_type == "market_overview":
            prompt = f"""
            Analyze the following stock market data and provide key insights:
            
            Total stocks tracked: {len(stock_data)}
            Recent price movements and trends observed.
            
            Please provide:
            1. Overall market sentiment analysis
            2. Key trends identified
            3. Risk assessment
            4. Investment recommendations (3-5 bullet points)
            5. Market outlook for the day
            
            Keep the analysis concise, professional, and actionable.
            """
        else:
            # Individual stock analysis
            stocks_summary = []
            for stock in stock_data[:10]:  # Analyze top 10 stocks
                stocks_summary.append(f"{stock['symbol']}: ₹{stock['price']}")
            
            prompt = f"""
            Analyze these specific stocks and their current prices:
            {', '.join(stocks_summary)}
            
            Please provide:
            1. Individual stock assessments
            2. Price movement patterns
            3. Trading recommendations
            4. Risk levels for each stock
            5. Portfolio diversification suggestions
            
            Focus on actionable insights for investors.
            """
        
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response
        
    except Exception as e:
        logging.error(f"AI analysis error: {str(e)}")
        return "AI analysis temporarily unavailable. Please check back later."

# Routes

@api_router.get("/")
async def root():
    return {"message": "Stock Analysis API is running"}

@api_router.get("/sheet/test-access/{sheet_id}")
async def test_sheet_access(sheet_id: str):
    """Test different methods to access Google Sheet"""
    try:
        import requests
        
        access_methods = []
        
        # Method 1: Try CSV export (requires public sharing)
        try:
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
            response = requests.get(csv_url, timeout=5)
            access_methods.append({
                "method": "CSV Export",
                "url": csv_url,
                "status": response.status_code,
                "accessible": response.status_code == 200
            })
        except Exception as e:
            access_methods.append({
                "method": "CSV Export",
                "error": str(e),
                "accessible": False
            })
        
        # Method 2: Try public view
        try:
            view_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
            response = requests.get(view_url, timeout=5)
            access_methods.append({
                "method": "Public View",
                "url": view_url,
                "status": response.status_code,
                "accessible": response.status_code == 200
            })
        except Exception as e:
            access_methods.append({
                "method": "Public View",
                "error": str(e),
                "accessible": False
            })
        
        return {
            "sheet_id": sheet_id,
            "access_methods": access_methods,
            "instructions": {
                "to_make_sheet_accessible": [
                    "1. Open your Google Sheet",
                    "2. Click 'Share' button (top right)",
                    "3. Change 'Restricted' to 'Anyone with the link'",
                    "4. Set permission to 'Viewer'",
                    "5. Copy the share link",
                    "Or use Google Sheets API with proper authentication"
                ]
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

async def fetch_live_boom_sheet_data(access_token: str = None):
    """Fetch live data from the Boom sheet using Google Sheets API with authentication"""
    try:
        sheet_id = "14ne0TE4FQ5s_NzWNa93uLN6OYBWh78iy3mCM0KTon1o"
        boom_sheet_gid = "304037161"  # Correct GID for Boom sheet from your URL
        
        if access_token:
            # Use authenticated Google Sheets API
            try:
                credentials = Credentials(token=access_token)
                service = build('sheets', 'v4', credentials=credentials)
                
                # Fetch data from the specific Boom sheet range
                range_name = "Boom!A:D"  # All columns A to D from Boom sheet
                
                result = service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=range_name
                ).execute()
                
                rows = result.get('values', [])
                
                if len(rows) > 1:
                    logging.info(f"Successfully fetched authenticated data: {len(rows)} rows")
                    return rows
                    
            except Exception as auth_error:
                logging.error(f"Authenticated fetch failed: {str(auth_error)}")
        
        # Fallback: Try with the specific GID from your URL
        try:
            import requests
            
            # Try the exact GID from your sheet URL
            gid_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={boom_sheet_gid}"
            response = requests.get(gid_url, timeout=10)
            
            if response.status_code == 200:
                import csv
                import io
                
                csv_data = response.text
                reader = csv.reader(io.StringIO(csv_data))
                rows = list(reader)
                
                if len(rows) > 1:
                    logging.info(f"Successfully fetched data via GID {boom_sheet_gid}: {len(rows)} rows")
                    return rows
            else:
                logging.warning(f"CSV export failed with status {response.status_code}")
                
        except Exception as e:
            logging.error(f"GID fetch error: {str(e)}")
        
        # Final fallback
        logging.warning("Could not fetch live data - authentication required")
        return None
            
    except Exception as e:
        logging.error(f"Live data fetch error: {str(e)}")
        return None

@api_router.post("/demo/sync")
async def demo_sync_stock_data():
    """Sync stock data - tries to fetch live data from Boom sheet with correct GID"""
    try:
        # Try to fetch live data first (no auth token in demo)
        live_data = await fetch_live_boom_sheet_data(access_token=None)
        
        if live_data and len(live_data) > 1:
            # Use live data from Boom sheet
            sheet_data = live_data
            data_source = "Live Boom Sheet (GID: 304037161)"
        else:
            # Fallback to sample data
            sheet_data = [
                ["Stock", "Price", "Time", "Alert"],
                ["SONACOMS", "412", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["HDFCAMC", "5768", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["DMART", "4610.1", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["BSE", "2059.6", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["CROMPTON", "299.4", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["TVSMOTOR", "3423.9", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["JINDALSTEL", "1057.8", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["LT", "3693", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["VEDL", "463.45", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["SONACOMS", "415.2", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["HDFCAMC", "5785.3", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["DMART", "4625.7", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["BSE", "2070.4", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["CROMPTON", "301.1", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["TVSMOTOR", "3445.2", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["JINDALSTEL", "1065.4", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["LT", "3708.5", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["VEDL", "468.9", "9:20:00 AM", "Alert for Ji FnO Check"],
                ["SONACOMS", "418.7", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["HDFCAMC", "5799.8", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["DMART", "4635.2", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["BSE", "2075.1", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["CROMPTON", "302.8", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["TVSMOTOR", "3457.6", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["JINDALSTEL", "1071.2", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["LT", "3715.9", "9:23:00 AM", "Alert for Ji FnO Check"],
                ["VEDL", "471.3", "9:23:00 AM", "Alert for Ji FnO Check"]
            ]
            data_source = "Sample Data (Authentication required for live access)"
        
        # Parse and store stock data
        parsed_stocks = parse_stock_data(sheet_data)
        
        # Clear old data and insert new
        await db.stocks.delete_many({})
        
        for stock in parsed_stocks:
            stock_data = StockData(**stock)
            await db.stocks.insert_one(prepare_for_mongo(stock_data.dict()))
        
        return {
            "message": f"Sync completed - loaded {len(parsed_stocks)} stock entries", 
            "count": len(parsed_stocks),
            "data_source": data_source,
            "sheet_rows": len(sheet_data) - 1,  # Exclude header
            "authentication_note": "Use Google Sign-in for live data access"
        }
        
    except Exception as e:
        logging.error(f"Demo sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Demo sync failed: {str(e)}")

@api_router.get("/demo/dashboard")
async def demo_get_dashboard_summary():
    """Demo dashboard - shows summary without authentication with new metrics"""
    try:
        # Get all stock data
        stock_cursor = db.stocks.find()
        all_stocks = await stock_cursor.to_list(length=None)
        
        if not all_stocks:
            return {
                "message": "No stock data available. Please sync first.",
                "total_stocks": 0,
                "recent_activity_count": 0,
                "max_appearances_count": 0,
                "recent_positive_count": 0,
                "latest_hour_stocks": [],
                "max_appearances_stocks": [],
                "recent_positive_stocks": [],
                "ai_market_insights": "Demo data not available. Please sync stock data first.",
                "last_updated": datetime.now(timezone.utc)
            }
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame([parse_from_mongo(stock) for stock in all_stocks])
        
        # Calculate metrics per stock symbol
        stock_metrics = []
        for symbol in df['symbol'].unique():
            symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
            
            if len(symbol_data) > 1:
                current_price = symbol_data.iloc[-1]['price']
                previous_price = symbol_data.iloc[0]['price']
                price_change = current_price - previous_price
                percentage_change = (price_change / previous_price) * 100 if previous_price > 0 else 0
                
                stock_metrics.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'previous_price': previous_price,
                    'price_change': price_change,
                    'percentage_change': percentage_change,
                    'data_points': len(symbol_data)
                })
        
        # Calculate the three requested metrics using relative time from sheet data
        
        # 1. Five stocks with latest data occurrences (most recent timestamps in sheet)
        latest_hour_stocks = []
        for stock in stock_metrics:
            symbol = stock['symbol']
            symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
            
            # Get latest timestamp for this stock from the available data
            if len(symbol_data) > 0:
                latest_timestamp = symbol_data.iloc[-1]['timestamp']
                stock_copy = stock.copy()
                stock_copy['latest_timestamp'] = latest_timestamp
                latest_hour_stocks.append(stock_copy)
        
        # Sort by most recent timestamp in the sheet data (not current time)
        latest_hour_stocks.sort(key=lambda x: x.get('latest_timestamp', datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        latest_hour_stocks = latest_hour_stocks[:10]  # Increased from 5 to 10
        
        # 2. First five stocks with maximum number of appearances
        stock_frequency = {}
        for stock_entry in all_stocks:
            symbol = stock_entry['symbol']
            stock_frequency[symbol] = stock_frequency.get(symbol, 0) + 1
        
        # Sort by frequency and take top 10
        max_appearances_stocks = []
        sorted_frequency = sorted(stock_frequency.items(), key=lambda x: x[1], reverse=True)[:10]  # Increased from 5 to 10
        for symbol, frequency in sorted_frequency:
            stock_info = next((s for s in stock_metrics if s['symbol'] == symbol), None)
            if stock_info:
                stock_copy = stock_info.copy()
                stock_copy['appearances'] = frequency
                max_appearances_stocks.append(stock_copy)
        
        # 3. Five stocks with positive price change and recent data occurrences (relative to sheet data)
        recent_positive_stocks = []
        
        # Find the latest timestamp in the entire dataset to determine what's "recent"
        all_timestamps = df['timestamp'].tolist()
        if all_timestamps:
            latest_overall_timestamp = max(all_timestamps)
            
            for stock in stock_metrics:
                symbol = stock['symbol']
                symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
                
                # Check if stock has positive price change and relatively recent data
                if stock['percentage_change'] > 0 and len(symbol_data) > 0:
                    latest_stock_timestamp = symbol_data.iloc[-1]['timestamp']
                    stock_copy = stock.copy()
                    stock_copy['latest_timestamp'] = latest_stock_timestamp
                    stock_copy['recency_score'] = latest_stock_timestamp  # Use timestamp as recency score
                    recent_positive_stocks.append(stock_copy)
            
            # Sort by combination of positive change and recency (most recent positive stocks)
            recent_positive_stocks.sort(key=lambda x: (x['recency_score'], x['percentage_change']), reverse=True)
        else:
            # Fallback if no timestamps available
            recent_positive_stocks = [s for s in stock_metrics if s['percentage_change'] > 0]
            recent_positive_stocks.sort(key=lambda x: x['percentage_change'], reverse=True)
        
        recent_positive_stocks = recent_positive_stocks[:10]  # Increased from 5 to 10
        
        # Generate AI insights with calculated data
        ai_insights = f"""🎯 Sheet Data Analysis:
        
📊 Latest Activity: {len(latest_hour_stocks)} stocks with most recent data entries
📈 Recent Positive: {len(recent_positive_stocks)} stocks with recent positive growth  
⚡ High Frequency: {len(max_appearances_stocks)} stocks with maximum appearances
🔍 Total Tracking: {len(stock_metrics)} unique stocks in sheet

💡 Key Observations:
• Latest Data: {"High activity" if len(latest_hour_stocks) > 3 else "Moderate activity"} based on sheet timestamps
• Positive Momentum: {len(recent_positive_stocks)} stocks showing recent gains in available data
• Market Frequency: High-appearance stocks indicate strong tracking focus
• Data Analysis: Based on chronological data patterns in your sheet
• Coverage: {"Excellent" if len(latest_hour_stocks) > 3 else "Good"} data availability from sheet"""
        
        dashboard_data = {
            "total_stocks": len(stock_metrics),
            "recent_activity_count": len(latest_hour_stocks),
            "max_appearances_count": len(max_appearances_stocks),
            "recent_positive_count": len(recent_positive_stocks),
            "latest_hour_stocks": latest_hour_stocks,
            "max_appearances_stocks": max_appearances_stocks,
            "recent_positive_stocks": recent_positive_stocks,
            "ai_market_insights": ai_insights,
            "last_updated": datetime.now(timezone.utc)
        }
        
        return dashboard_data
        
    except Exception as e:
        logging.error(f"Demo dashboard error: {str(e)}")
        return {
            "total_stocks": 0,
            "recent_activity_count": 0,
            "max_appearances_count": 0,
            "recent_positive_count": 0,
            "latest_hour_stocks": [],
            "max_appearances_stocks": [],
            "recent_positive_stocks": [],
            "ai_market_insights": f"Demo dashboard error: {str(e)}",
            "last_updated": datetime.now(timezone.utc)
        }

# Emergent Auth Integration
@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Process session from Emergent Auth"""
    try:
        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing session ID")
        
        # Call Emergent auth service
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data',
                headers={'X-Session-ID': session_id}
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=401, detail="Invalid session")
                
                user_data = await resp.json()
        
        # Create session token and store user
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=7)
        
        user = User(
            email=user_data['email'],
            name=user_data['name'],
            picture=user_data.get('picture'),
            session_token=session_token,
            expires_at=expires_at
        )
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": user.email})
        if not existing_user:
            await db.users.insert_one(prepare_for_mongo(user.dict()))
        else:
            # Update session token
            await db.users.update_one(
                {"email": user.email},
                {"$set": {
                    "session_token": session_token,
                    "expires_at": expires_at.isoformat()
                }}
            )
        
        # Set cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            max_age=7*24*60*60,
            httponly=True,
            secure=True,
            samesite="none",
            path="/"
        )
        
        return {"message": "Session created", "user": user.dict()}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    """Logout user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    await db.users.delete_one({"session_token": current_user.session_token})
    response.delete_cookie("session_token", path="/")
    return {"message": "Logged out successfully"}

# Google OAuth for Sheets Access
@api_router.post("/auth/google-sheets")
async def authorize_google_sheets(request: Request, current_user: User = Depends(get_current_user)):
    """Start Google OAuth flow for Sheets access"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # In production, implement proper OAuth flow
    # For now, we'll use a simplified approach
    return {
        "message": "Google Sheets authorization required",
        "auth_url": f"https://auth.emergentagent.com/google?user_id={current_user.id}&scopes=sheets"
    }

# Stock Data Routes
@api_router.post("/stocks/sync")
async def sync_stock_data(demo: bool = False, current_user: User = Depends(get_current_user)):
    """Sync stock data from Google Sheets with authentication"""
    if not demo and not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        access_token = None
        if current_user and current_user.google_access_token:
            access_token = current_user.google_access_token
        
        # Fetch live data from authenticated Google Sheets
        live_data = await fetch_live_boom_sheet_data(access_token)
        
        if live_data and len(live_data) > 1:
            sheet_data = live_data
            data_source = "Authenticated Google Sheets"
        else:
            # Fallback to sample data if authentication fails
            sheet_data = [
                ["Stock", "Price", "Time", "Alert"],
                ["SONACOMS", "412", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["HDFCAMC", "5768", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["DMART", "4610.1", "9:17:00 AM", "Alert for Ji FnO Check"],
                ["BSE", "2059.6", "9:17:00 AM", "Alert for Ji FnO Check"],
            ]
            data_source = "Sample Data (Authentication required for live data)"
        
        # Parse and store stock data
        parsed_stocks = parse_stock_data(sheet_data)
        
        # Clear old data and insert new
        await db.stocks.delete_many({})
        
        for stock in parsed_stocks:
            stock_data = StockData(**stock)
            await db.stocks.insert_one(prepare_for_mongo(stock_data.dict()))
        
        return {
            "message": f"Sync completed - loaded {len(parsed_stocks)} stock entries", 
            "count": len(parsed_stocks),
            "data_source": data_source,
            "authentication": "required" if not access_token else "authenticated"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@api_router.get("/stocks/dashboard")
async def get_dashboard_summary(demo: bool = False, current_user: User = Depends(get_current_user)):
    """Get dashboard summary with key metrics"""
    if not demo and not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get all stock data
        stock_cursor = db.stocks.find()
        all_stocks = await stock_cursor.to_list(length=None)
        
        if not all_stocks:
            return {
                "message": "No stock data available. Please sync first.",
                "total_stocks": 0,
                "top_gainers": [],
                "top_losers": [],
                "best_performers": []
            }
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame([parse_from_mongo(stock) for stock in all_stocks])
        
        # Calculate metrics per stock symbol
        stock_metrics = []
        for symbol in df['symbol'].unique():
            symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
            
            if len(symbol_data) > 1:
                current_price = symbol_data.iloc[-1]['price']
                previous_price = symbol_data.iloc[0]['price']
                price_change = current_price - previous_price
                percentage_change = (price_change / previous_price) * 100 if previous_price > 0 else 0
                
                stock_metrics.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'previous_price': previous_price,
                    'price_change': price_change,
                    'percentage_change': percentage_change,
                    'data_points': len(symbol_data)
                })
        
        # Sort for different categories
        sorted_by_percentage = sorted(stock_metrics, key=lambda x: x['percentage_change'], reverse=True)
        sorted_by_absolute = sorted(stock_metrics, key=lambda x: x['price_change'], reverse=True)
        
        # Top gainers (percentage)
        top_gainers = sorted_by_percentage[:5]
        
        # Top losers (percentage)
        top_losers = sorted_by_percentage[-5:]
        
        # Best performers (absolute price increase)
        best_performers = sorted_by_absolute[:5]
        
        # Calculate portfolio metrics
        total_portfolio_change = sum(stock['price_change'] for stock in stock_metrics)
        avg_percentage_change = np.mean([stock['percentage_change'] for stock in stock_metrics]) if stock_metrics else 0
        
        # Generate AI insights
        ai_insights = await generate_ai_insights(stock_metrics, "market_overview")
        
        dashboard_data = DashboardSummary(
            total_stocks=len(stock_metrics),
            top_gainers=top_gainers,
            top_losers=top_losers,
            best_performers=best_performers,
            total_portfolio_change=round(total_portfolio_change, 2),
            total_portfolio_percentage=round(avg_percentage_change, 2),
            ai_market_insights=ai_insights,
            last_updated=datetime.now(timezone.utc)
        )
        
        return dashboard_data.dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard error: {str(e)}")

@api_router.get("/stocks/analysis/{symbol}")
async def get_stock_analysis(symbol: str, current_user: User = Depends(get_current_user)):
    """Get detailed analysis for a specific stock"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get stock data for symbol
        stock_cursor = db.stocks.find({"symbol": symbol})
        stock_data = await stock_cursor.to_list(length=None)
        
        if not stock_data:
            raise HTTPException(status_code=404, detail="Stock not found")
        
        # Convert and analyze
        df = pd.DataFrame([parse_from_mongo(stock) for stock in stock_data])
        df = df.sort_values('timestamp')
        
        # Calculate metrics
        current_price = df.iloc[-1]['price']
        if len(df) > 1:
            previous_price = df.iloc[0]['price']
            price_change = current_price - previous_price
            percentage_change = (price_change / previous_price) * 100
        else:
            previous_price = current_price
            price_change = 0
            percentage_change = 0
        
        # Determine trend
        if percentage_change > 2:
            trend = "bullish"
        elif percentage_change < -2:
            trend = "bearish"
        else:
            trend = "neutral"
        
        # Generate AI insights for this specific stock
        ai_insights = await generate_ai_insights([{
            'symbol': symbol,
            'price': current_price,
            'change': price_change,
            'percentage_change': percentage_change
        }], "individual_stock")
        
        analysis = StockAnalysis(
            symbol=symbol,
            current_price=current_price,
            price_change=price_change,
            percentage_change=percentage_change,
            analysis_type="daily",
            ai_insights=ai_insights,
            trend=trend
        )
        
        return analysis.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@api_router.get("/stocks/filters")
async def get_filtered_stocks(
    filter_type: str = "percentage_gains",  # percentage_gains, absolute_gains, consistent_growth
    limit: int = 10,
    demo: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Get filtered stock lists based on criteria"""
    if not demo and not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get all stock data
        stock_cursor = db.stocks.find()
        all_stocks = await stock_cursor.to_list(length=None)
        
        if not all_stocks:
            return {"message": "No data available", "stocks": []}
        
        # Convert to DataFrame
        df = pd.DataFrame([parse_from_mongo(stock) for stock in all_stocks])
        
        # Calculate metrics per stock
        stock_metrics = []
        for symbol in df['symbol'].unique():
            symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
            
            if len(symbol_data) > 1:
                current_price = symbol_data.iloc[-1]['price']
                first_price = symbol_data.iloc[0]['price']
                price_change = current_price - first_price
                percentage_change = (price_change / first_price) * 100 if first_price > 0 else 0
                
                # Calculate consistency (lower standard deviation = more consistent)
                price_std = symbol_data['price'].std()
                consistency_score = 100 - min(price_std, 100)  # Inverse of volatility
                
                stock_metrics.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'price_change': price_change,
                    'percentage_change': percentage_change,
                    'consistency_score': consistency_score,
                    'data_points': len(symbol_data),
                    'volatility': price_std
                })
        
        # Calculate additional metrics for trading analysis
        current_time = datetime.now(timezone.utc)
        
        # Time-based analysis
        for stock in stock_metrics:
            symbol = stock['symbol']
            symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
            
            # Calculate frequency
            stock['frequency'] = len(symbol_data)
            
            # Time-based growth calculation
            stock['last_5min_growth'] = 0
            stock['last_15min_growth'] = 0
            stock['last_1hour_growth'] = 0
            
            if len(symbol_data) >= 2:
                recent_data = symbol_data.tail(3)  # Last 3 entries
                if len(recent_data) >= 2:
                    stock['last_5min_growth'] = ((recent_data.iloc[-1]['price'] - recent_data.iloc[-2]['price']) / recent_data.iloc[-2]['price']) * 100
                
                if len(recent_data) >= 3:
                    stock['last_15min_growth'] = ((recent_data.iloc[-1]['price'] - recent_data.iloc[-3]['price']) / recent_data.iloc[-3]['price']) * 100
                
                # Last hour growth (assuming each entry is ~3 minutes apart)
                hour_data = symbol_data.tail(20) if len(symbol_data) >= 20 else symbol_data
                if len(hour_data) >= 2:
                    stock['last_1hour_growth'] = ((hour_data.iloc[-1]['price'] - hour_data.iloc[0]['price']) / hour_data.iloc[0]['price']) * 100
            
            # Attractiveness score (combination of growth, consistency, and activity)
            stock['attractiveness_score'] = (
                stock['percentage_change'] * 0.4 + 
                stock['consistency_score'] * 0.3 + 
                (stock['frequency'] / 10) * 0.3
            )
        
        # Apply filters
        if filter_type == "consistent_growth":
            # Most consistent growth over time
            growth_stocks = [s for s in stock_metrics if s['percentage_change'] > 0]
            filtered_stocks = sorted(growth_stocks, key=lambda x: x['consistency_score'], reverse=True)[:limit]
        elif filter_type == "most_frequent":
            # Stocks that repeated maximum times
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['frequency'], reverse=True)[:limit]
        elif filter_type == "positive_growth":
            # Stocks with positive price growth over the day
            filtered_stocks = sorted([s for s in stock_metrics if s['percentage_change'] > 0], 
                                   key=lambda x: x['percentage_change'], reverse=True)[:limit]
        elif filter_type == "max_current_movement":
            # Maximum current movement (highest percentage change - both positive and negative)
            filtered_stocks = sorted(stock_metrics, key=lambda x: abs(x['percentage_change']), reverse=True)[:limit]
        elif filter_type == "max_price_change":
            # Maximum absolute price change in rupees
            filtered_stocks = sorted(stock_metrics, key=lambda x: abs(x['price_change']), reverse=True)[:limit]
        elif filter_type == "max_appearances":
            # Maximum number of appearances in the sheet
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['frequency'], reverse=True)[:limit]
        elif filter_type == "last_5min":
            # Highest growth in last 5 minutes
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['last_5min_growth'], reverse=True)[:limit]
        elif filter_type == "last_15min":
            # Highest growth in last 15 minutes
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['last_15min_growth'], reverse=True)[:limit]
        elif filter_type == "last_1hour":
            # Highest growth in last 1 hour
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['last_1hour_growth'], reverse=True)[:limit]
        elif filter_type == "most_attractive":
            # Most attractive stocks to buy based on all parameters
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['attractiveness_score'], reverse=True)[:limit]
        elif filter_type == "active_positive":
            # Most active stocks with positive growth (current time preference)
            active_positive = [s for s in stock_metrics if s['percentage_change'] > 0 and s['frequency'] >= 2]
            filtered_stocks = sorted(active_positive, 
                                   key=lambda x: (x['frequency'] * 0.6 + x['percentage_change'] * 0.4), 
                                   reverse=True)[:limit]
        else:
            filtered_stocks = stock_metrics[:limit]
        
        return {
            "filter_type": filter_type,
            "total_stocks": len(stock_metrics),
            "filtered_count": len(filtered_stocks),
            "stocks": filtered_stocks
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Filter error: {str(e)}")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()