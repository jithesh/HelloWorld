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
    """Fetch data from Google Sheets"""
    try:
        credentials = Credentials(token=access_token)
        service = build('sheets', 'v4', credentials=credentials)
        
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()
        
        return result.get('values', [])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch sheet data: {str(e)}")

def parse_stock_data(raw_data):
    """Parse the comma-separated stock data from Google Sheets"""
    parsed_stocks = []
    
    for row in raw_data[1:]:  # Skip header
        if len(row) >= 4:
            stocks = row[0].split(',')
            prices_str = row[1].split(',')
            timestamp_str = row[2]
            alert_id = row[3]
            
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
            
            # Parse individual stock prices
            for i, stock in enumerate(stocks):
                if i < len(prices_str):
                    try:
                        price = float(prices_str[i])
                        parsed_stocks.append({
                            'symbol': stock.strip(),
                            'price': price,
                            'timestamp': timestamp,
                            'alert_id': alert_id,
                            'raw_data': {
                                'original_row': row,
                                'stock_index': i
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
    """Sync stock data from Google Sheets"""
    if not demo and not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # For demo, we'll simulate the Google Sheets data structure
        # In production, this would fetch from the actual Google Sheet
        sheet_id = "14ne0TE4FQ5s_NzWNa93uLN6OYBWh78iy3mCM0KTon1o"
        
        # Simulate fetched data (based on the actual sheet structure)
        sample_data = [
            ["Stock", "Price", "Time", "Alert"],
            ["NETWEB,CARTRADE,RITES,PIGL,VERTOZ", "3647,2499.7,267,180.4,76.13", "9:18:00 AM", "Alert for Ji ID ADX3"],
            ["VERANDA,CARTRADE,RITES,GODREJAGRO", "215.61,2501.4,268.73,718.95", "9:21:00 AM", "Alert for Ji ID ADX3"],
            ["STALLION,NETWEB,SJS,CARTRADE", "213.23,3640.6,1489.8,2517.3", "9:24:00 AM", "Alert for Ji ID ADX3"],
        ]
        
        # Parse and store stock data
        parsed_stocks = parse_stock_data(sample_data)
        
        # Clear old data and insert new
        await db.stocks.delete_many({})
        
        for stock in parsed_stocks:
            stock_data = StockData(**stock)
            await db.stocks.insert_one(prepare_for_mongo(stock_data.dict()))
        
        return {"message": f"Synced {len(parsed_stocks)} stock entries", "count": len(parsed_stocks)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@api_router.get("/stocks/dashboard")
async def get_dashboard_summary(current_user: User = Depends(get_current_user)):
    """Get dashboard summary with key metrics"""
    if not current_user:
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
    current_user: User = Depends(get_current_user)
):
    """Get filtered stock lists based on criteria"""
    if not current_user:
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
        
        # Apply filters
        if filter_type == "percentage_gains":
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['percentage_change'], reverse=True)[:limit]
        elif filter_type == "absolute_gains":
            filtered_stocks = sorted(stock_metrics, key=lambda x: x['price_change'], reverse=True)[:limit]
        elif filter_type == "consistent_growth":
            # Filter stocks with positive growth and low volatility
            growth_stocks = [s for s in stock_metrics if s['percentage_change'] > 0]
            filtered_stocks = sorted(growth_stocks, key=lambda x: x['consistency_score'], reverse=True)[:limit]
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