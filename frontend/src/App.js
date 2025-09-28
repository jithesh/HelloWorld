import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from './components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select';
import { Progress } from './components/ui/progress';
import { Alert, AlertDescription } from './components/ui/alert';
import { Skeleton } from './components/ui/skeleton';
import { Separator } from './components/ui/separator';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Auth Context
const AuthContext = React.createContext();

const useAuth = () => {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      // Check for session_id in URL fragment first
      const hash = window.location.hash;
      const sessionIdMatch = hash.match(/session_id=([^&]+)/);
      
      if (sessionIdMatch) {
        const sessionId = sessionIdMatch[1];
        setLoading(true);
        
        // Process session ID
        const response = await axios.post(`${API}/auth/session`, {}, {
          headers: { 'X-Session-ID': sessionId }
        });
        
        setUser(response.data.user);
        // Clean up URL
        window.location.hash = '';
        window.history.replaceState({}, document.title, window.location.pathname);
      } else {
        // Check existing session
        const response = await axios.get(`${API}/auth/me`);
        setUser(response.data);
      }
    } catch (error) {
      console.log('Not authenticated');
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = () => {
    const redirectUrl = encodeURIComponent(window.location.origin + '/dashboard');
    window.location.href = `https://auth.emergentagent.com/?redirect=${redirectUrl}`;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`);
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

// Stock Dashboard Components
const DashboardSummary = ({ summary, onRefresh, loading }) => {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Market Pulse Dashboard</h2>
          <p className="text-muted-foreground">
            Real-time stock analysis with AI-powered insights
          </p>
        </div>
        <Button 
          onClick={onRefresh} 
          disabled={loading}
          className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700"
        >
          {loading ? 'Syncing...' : 'Sync Data'}
        </Button>
      </div>

      {/* Key Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Stocks</CardTitle>
            <div className="h-4 w-4 bg-blue-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-700">
              {summary?.total_stocks || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Active tracking
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Portfolio Change</CardTitle>
            <div className="h-4 w-4 bg-emerald-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-700">
              ₹{summary?.total_portfolio_change || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {summary?.total_portfolio_percentage >= 0 ? '+' : ''}{summary?.total_portfolio_percentage?.toFixed(2) || 0}% today
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Top Gainer</CardTitle>
            <div className="h-4 w-4 bg-amber-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-700">
              {summary?.top_gainers?.[0]?.symbol || 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground">
              +{summary?.top_gainers?.[0]?.percentage_change?.toFixed(2) || 0}%
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-red-50 to-rose-50 border-red-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Top Loser</CardTitle>
            <div className="h-4 w-4 bg-red-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-700">
              {summary?.top_losers?.[0]?.symbol || 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground">
              {summary?.top_losers?.[0]?.percentage_change?.toFixed(2) || 0}%
            </p>
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      {summary?.ai_market_insights && (
        <Card className="bg-gradient-to-br from-purple-50 to-violet-50 border-purple-200">
          <CardHeader>
            <CardTitle className="text-lg text-purple-800 flex items-center gap-2">
              🤖 AI Market Insights
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {summary.ai_market_insights}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

const StockList = ({ title, stocks, type }) => {
  const getCardStyle = () => {
    switch (type) {
      case 'gainers':
        return 'border-emerald-200 bg-gradient-to-r from-emerald-50 to-green-50';
      case 'losers':
        return 'border-red-200 bg-gradient-to-r from-red-50 to-rose-50';
      case 'performers':
        return 'border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50';
      default:
        return 'border-gray-200';
    }
  };

  const getBadgeColor = (change) => {
    if (change > 0) return 'bg-emerald-100 text-emerald-800';
    if (change < 0) return 'bg-red-100 text-red-800';
    return 'bg-gray-100 text-gray-800';
  };

  return (
    <Card className={getCardStyle()}>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription>
          {type === 'gainers' && 'Best performing stocks by percentage'}
          {type === 'losers' && 'Stocks with highest losses'}
          {type === 'performers' && 'Top absolute price gainers'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {stocks?.length > 0 ? (
            stocks.map((stock, index) => (
              <div key={stock.symbol} className="flex items-center justify-between p-3 rounded-lg bg-white/60 backdrop-blur-sm">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm font-semibold">
                    {index + 1}
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900">{stock.symbol}</div>
                    <div className="text-sm text-gray-600">₹{stock.current_price?.toFixed(2)}</div>
                  </div>
                </div>
                <div className="text-right">
                  <Badge className={getBadgeColor(stock.percentage_change)}>
                    {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                  </Badge>
                  <div className="text-xs text-gray-600 mt-1">
                    ₹{stock.price_change > 0 ? '+' : ''}{stock.price_change?.toFixed(2)}
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-gray-500">
              No data available
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

const FilteredStocks = () => {
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [filterType, setFilterType] = useState('percentage_gains');
  const [loading, setLoading] = useState(false);

  const fetchFilteredStocks = async (type) => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/stocks/filters`, {
        params: { filter_type: type, limit: 10 }
      });
      setFilteredStocks(response.data.stocks || []);
    } catch (error) {
      console.error('Error fetching filtered stocks:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFilteredStocks(filterType);
  }, [filterType]);

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <div>
            <CardTitle>Filtered Stock Analysis</CardTitle>
            <CardDescription>
              Filter stocks by different performance criteria
            </CardDescription>
          </div>
          <Select value={filterType} onValueChange={(value) => setFilterType(value)}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="percentage_gains">Percentage Gains</SelectItem>
              <SelectItem value="absolute_gains">Absolute Gains</SelectItem>
              <SelectItem value="consistent_growth">Consistent Growth</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {filteredStocks.length > 0 ? (
              filteredStocks.map((stock, index) => (
                <div key={stock.symbol} className="flex items-center justify-between p-4 rounded-lg border bg-gradient-to-r from-gray-50 to-white">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-sm font-semibold text-blue-700">
                      {index + 1}
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">{stock.symbol}</div>
                      <div className="text-sm text-gray-600">₹{stock.current_price?.toFixed(2)}</div>
                    </div>
                  </div>
                  <div className="flex gap-4 items-center">
                    <div className="text-right">
                      <div className="text-sm font-medium">Change</div>
                      <div className="text-sm text-gray-600">
                        {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                      </div>
                    </div>
                    {filterType === 'consistent_growth' && (
                      <div className="text-right">
                        <div className="text-sm font-medium">Consistency</div>
                        <div className="text-sm text-gray-600">
                          {stock.consistency_score?.toFixed(1)}/100
                        </div>
                      </div>
                    )}
                    <Badge 
                      variant={stock.percentage_change >= 0 ? "default" : "destructive"}
                      className={stock.percentage_change >= 0 ? "bg-emerald-100 text-emerald-800" : ""}
                    >
                      ₹{stock.price_change > 0 ? '+' : ''}{stock.price_change?.toFixed(2)}
                    </Badge>
                  </div>
                </div>
              ))
            ) : (
              <Alert>
                <AlertDescription>
                  No stocks match the selected filter criteria. Try syncing data first.
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const Dashboard = () => {
  const { user } = useAuth();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      // Try authenticated dashboard first, fall back to demo dashboard
      try {
        const response = await axios.get(`${API}/stocks/dashboard`);
        setDashboardData(response.data);
      } catch (authError) {
        if (authError.response?.status === 401) {
          // Use demo dashboard if not authenticated
          const response = await axios.get(`${API}/demo/dashboard`);
          setDashboardData(response.data);
        } else {
          throw authError;
        }
      }
    } catch (error) {
      console.error('Dashboard error:', error);
      setError(error.response?.data?.detail || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  const syncStockData = async () => {
    setLoading(true);
    try {
      // Try authenticated sync first, fall back to demo sync
      try {
        await axios.post(`${API}/stocks/sync`);
      } catch (authError) {
        if (authError.response?.status === 401) {
          // Use demo sync if not authenticated
          await axios.post(`${API}/demo/sync`);
        } else {
          throw authError;
        }
      }
      // Refresh dashboard after sync
      await fetchDashboard();
    } catch (error) {
      console.error('Sync error:', error);
      setError('Failed to sync stock data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  if (loading && !dashboardData) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          <Skeleton className="h-32 w-full" />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <div className="max-w-7xl mx-auto p-6">
        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertDescription className="text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full lg:w-400 grid-cols-3 bg-white/80 backdrop-blur-sm">
            <TabsTrigger value="overview" data-testid="overview-tab">Overview</TabsTrigger>
            <TabsTrigger value="analysis" data-testid="analysis-tab">Analysis</TabsTrigger>
            <TabsTrigger value="filters" data-testid="filters-tab">Filters</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            <DashboardSummary 
              summary={dashboardData} 
              onRefresh={syncStockData}
              loading={loading}
            />

            <div className="grid gap-6 lg:grid-cols-3">
              <StockList 
                title="🚀 Top Gainers" 
                stocks={dashboardData?.top_gainers} 
                type="gainers"
              />
              <StockList 
                title="📉 Top Losers" 
                stocks={dashboardData?.top_losers} 
                type="losers"
              />
              <StockList 
                title="💎 Best Performers" 
                stocks={dashboardData?.best_performers} 
                type="performers"
              />
            </div>
          </TabsContent>

          <TabsContent value="analysis" className="space-y-6">
            <Card className="bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-200">
              <CardHeader>
                <CardTitle className="text-xl">📊 Market Analysis</CardTitle>
                <CardDescription>
                  Comprehensive stock market analysis with AI insights
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dashboardData?.ai_market_insights ? (
                  <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {dashboardData.ai_market_insights}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    Sync data to view AI analysis
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="filters" className="space-y-6">
            <FilteredStocks />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

const LandingPage = () => {
  const { login } = useAuth();

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900 flex items-center justify-center p-6">
      <div className="max-w-4xl mx-auto text-center">
        <div className="mb-8">
          <h1 className="text-6xl font-bold text-white mb-4 leading-tight">
            Market <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-400">Pulse</span>
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto leading-relaxed">
            Transform your Google Sheets stock data into powerful AI-driven insights. 
            Track performance, analyze trends, and make smarter investment decisions.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6 mb-12">
          <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20">
            <div className="text-4xl mb-4">📊</div>
            <h3 className="text-lg font-semibold text-white mb-2">Real-time Analysis</h3>
            <p className="text-gray-300 text-sm">
              Connect your Google Sheets and get instant stock analysis with AI-powered insights
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20">
            <div className="text-4xl mb-4">🚀</div>
            <h3 className="text-lg font-semibold text-white mb-2">Smart Filtering</h3>
            <p className="text-gray-300 text-sm">
              Filter top performers by gains, consistency, and growth patterns
            </p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20">
            <div className="text-4xl mb-4">🤖</div>
            <h3 className="text-lg font-semibold text-white mb-2">AI Insights</h3>
            <p className="text-gray-300 text-sm">
              Get personalized investment recommendations powered by advanced AI
            </p>
          </div>
        </div>

        <Button 
          onClick={login}
          size="lg"
          className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white px-8 py-4 text-lg font-semibold shadow-2xl"
          data-testid="get-started-btn"
        >
          Get Started with Google
        </Button>
        
        <p className="text-gray-400 text-sm mt-4">
          Secure authentication • No data stored • Privacy first
        </p>
      </div>
    </main>
  );
};

const LoadingScreen = () => (
  <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center">
    <div className="text-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
      <p className="text-gray-600">Loading Market Pulse...</p>
    </div>
  </div>
);

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="App">
          <Routes>
            <Route path="/" element={<AppRouter />} />
            <Route path="/dashboard" element={<AppRouter />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

const AppRouter = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!user) {
    return <LandingPage />;
  }

  return <Dashboard />;
};

export default App;