import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
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
    // Add Google Sheets scope for accessing the Boom sheet
    window.location.href = `https://auth.emergentagent.com/?redirect=${redirectUrl}&scopes=https://www.googleapis.com/auth/spreadsheets.readonly`;
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
const DashboardSummary = ({ summary, onRefresh, loading, autoSyncEnabled, toggleAutoSync, lastSyncTime }) => {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Stock Screener & Options Analysis</h2>
          <p className="text-muted-foreground">
            Real-time stock screening for option trading opportunities
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-2">
            <Button 
              onClick={onRefresh} 
              disabled={loading}
              className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700"
            >
              {loading ? 'Syncing...' : 'Sync Now'}
            </Button>
            <Button 
              onClick={toggleAutoSync}
              variant={autoSyncEnabled ? "default" : "outline"}
              className={autoSyncEnabled ? "bg-green-600 hover:bg-green-700" : ""}
            >
              Auto-Sync {autoSyncEnabled ? 'ON' : 'OFF'}
            </Button>
          </div>
          <div className="text-xs text-gray-500 text-right">
            {lastSyncTime && (
              <p>Last synced: {lastSyncTime.toLocaleTimeString()}</p>
            )}
            {autoSyncEnabled && (
              <p className="text-green-600">⚡ Auto-sync every 30s</p>
            )}
          </div>
        </div>
      </div>

      {/* Key Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Stocks Tracked</CardTitle>
            <div className="h-4 w-4 bg-blue-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-700">
              {summary?.total_stocks || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Live monitoring
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Recent Activity</CardTitle>
            <div className="h-4 w-4 bg-emerald-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {summary?.latest_hour_stocks?.length > 0 ? (
                summary.latest_hour_stocks.slice(0, 5).map((stock, index) => (
                  <div key={stock.symbol} className="text-sm font-semibold text-emerald-700">
                    {index + 1}. {stock.symbol} (+{stock.percentage_change?.toFixed(2) || 0}%)
                  </div>
                ))
              ) : (
                <div className="text-sm text-gray-500">No recent activity</div>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Last hour updates
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">High Frequency</CardTitle>
            <div className="h-4 w-4 bg-amber-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {summary?.max_appearances_stocks?.length > 0 ? (
                summary.max_appearances_stocks.slice(0, 5).map((stock, index) => (
                  <div key={stock.symbol} className="text-sm font-semibold text-amber-700">
                    {index + 1}. {stock.symbol} ({stock.appearances || stock.frequency || 0}x)
                  </div>
                ))
              ) : (
                <div className="text-sm text-gray-500">No frequency data</div>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Maximum appearances
            </p>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-red-50 to-rose-50 border-red-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Recent Gains</CardTitle>
            <div className="h-4 w-4 bg-red-500 rounded-full"></div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {summary?.recent_positive_stocks?.length > 0 ? (
                summary.recent_positive_stocks.slice(0, 5).map((stock, index) => (
                  <div key={stock.symbol} className="text-sm font-semibold text-red-700">
                    {index + 1}. {stock.symbol} (+{stock.percentage_change?.toFixed(2) || 0}%)
                  </div>
                ))
              ) : (
                <div className="text-sm text-gray-500">No recent gains</div>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Last 15min positive
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
      case 'recent':
        return 'border-emerald-200 bg-gradient-to-r from-emerald-50 to-green-50';
      case 'frequent':
        return 'border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50';
      case 'positive':
        return 'border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50';
      case 'negative':
        return 'border-red-200 bg-gradient-to-r from-red-50 to-rose-50';
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
          {type === 'recent' && 'Latest data occurrences in the last hour'}
          {type === 'frequent' && 'Stocks with maximum number of appearances'}
          {type === 'positive' && 'Positive price changes in last 15 minutes'}
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
                  {type === 'recent' && (
                    <div>
                      <Badge variant="outline" className="text-xs">Latest Update</Badge>
                      <div className="text-xs text-gray-600 mt-1">
                        {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                      </div>
                    </div>
                  )}
                  {type === 'frequent' && (
                    <div>
                      <Badge variant="secondary" className="text-xs">
                        {stock.appearances || stock.frequency || 0} times
                      </Badge>
                      <div className="text-xs text-gray-600 mt-1">
                        {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                      </div>
                    </div>
                  )}
                  {type === 'positive' && (
                    <div>
                      <Badge className={getBadgeColor(stock.percentage_change)}>
                        +{stock.percentage_change?.toFixed(2)}%
                      </Badge>
                      <div className="text-xs text-gray-600 mt-1">
                        ₹+{stock.price_change?.toFixed(2)}
                      </div>
                    </div>
                  )}
                  {!['recent', 'frequent', 'positive'].includes(type) && (
                    <div>
                      <Badge className={getBadgeColor(stock.percentage_change)}>
                        {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                      </Badge>
                      <div className="text-xs text-gray-600 mt-1">
                        ₹{stock.price_change > 0 ? '+' : ''}{stock.price_change?.toFixed(2)}
                      </div>
                    </div>
                  )}
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
  const [loading, setLoading] = useState(true);
  
  // Use same logic as parent Dashboard component
  const isDemoMode = useMemo(() => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('demo') === 'true';
  }, []);

  const fetchFilteredStocks = async (type) => {
    setLoading(true);
    try {
      const params = { filter_type: type, limit: 10 };
      if (isDemoMode) {
        params.demo = true;
      }
      
      const response = await axios.get(`${API}/stocks/filters`, { params });
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
              <SelectItem value="consistent_growth">Most Consistent Growth</SelectItem>
              <SelectItem value="most_frequent">Most Frequently Tracked</SelectItem>
              <SelectItem value="positive_growth">Positive Day Growth</SelectItem>
              <SelectItem value="max_current_movement">Maximum Current Movement</SelectItem>
              <SelectItem value="max_price_change">Maximum Price Change</SelectItem>
              <SelectItem value="max_appearances">Maximum Appearances</SelectItem>
              <SelectItem value="last_5min">Last 5 Minutes Growth</SelectItem>
              <SelectItem value="last_15min">Last 15 Minutes Growth</SelectItem>
              <SelectItem value="last_1hour">Last 1 Hour Growth</SelectItem>
              <SelectItem value="most_attractive">Most Attractive to Buy</SelectItem>
              <SelectItem value="active_positive">Most Active & Positive</SelectItem>
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
                      <div className="text-sm font-medium">
                        {filterType === 'most_frequent' ? 'Frequency' : 
                         filterType === 'max_appearances' ? 'Appearances' :
                         filterType === 'max_current_movement' ? 'Movement' :
                         filterType === 'max_price_change' ? 'Price Change' :
                         filterType === 'last_5min' ? '5min Growth' :
                         filterType === 'last_15min' ? '15min Growth' :
                         filterType === 'last_1hour' ? '1hr Growth' :
                         filterType === 'most_attractive' ? 'Score' :
                         'Day Change'}
                      </div>
                      <div className="text-sm text-gray-600">
                        {filterType === 'most_frequent' ? `${stock.frequency || 0} alerts` :
                         filterType === 'max_appearances' ? `${stock.frequency || 0} times` :
                         filterType === 'max_current_movement' ? `${Math.abs(stock.percentage_change || 0).toFixed(2)}%` :
                         filterType === 'max_price_change' ? `₹${Math.abs(stock.price_change || 0).toFixed(2)}` :
                         filterType === 'last_5min' ? `${stock.last_5min_growth?.toFixed(2) || 0}%` :
                         filterType === 'last_15min' ? `${stock.last_15min_growth?.toFixed(2) || 0}%` :
                         filterType === 'last_1hour' ? `${stock.last_1hour_growth?.toFixed(2) || 0}%` :
                         filterType === 'most_attractive' ? `${stock.attractiveness_score?.toFixed(1) || 0}/10` :
                         `${stock.percentage_change > 0 ? '+' : ''}${stock.percentage_change?.toFixed(2)}%`}
                      </div>
                    </div>
                    {(filterType === 'consistent_growth' || filterType === 'active_positive') && (
                      <div className="text-right">
                        <div className="text-sm font-medium">
                          {filterType === 'consistent_growth' ? 'Consistency' : 'Activity'}
                        </div>
                        <div className="text-sm text-gray-600">
                          {filterType === 'consistent_growth' ? 
                           `${stock.consistency_score?.toFixed(1) || 0}/100` :
                           `${stock.frequency || 0} times`}
                        </div>
                      </div>
                    )}
                    <div className="flex flex-col gap-1">
                      <Badge 
                        variant={stock.percentage_change >= 0 ? "default" : "destructive"}
                        className={stock.percentage_change >= 0 ? "bg-emerald-100 text-emerald-800" : ""}
                      >
                        ₹{stock.current_price?.toFixed(2)}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {stock.percentage_change > 0 ? '+' : ''}{stock.percentage_change?.toFixed(2)}%
                      </Badge>
                    </div>
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(true);
  const [lastSyncTime, setLastSyncTime] = useState(null);
  const hasInitialized = useRef(false);
  const autoSyncInterval = useRef(null);
  
  // Use useMemo to prevent recalculation on every render
  const isDemoMode = useMemo(() => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('demo') === 'true' || !user;
  }, [user]);

  const fetchDashboard = async () => {
    console.log('Starting fetchDashboard, setting loading to true');
    setLoading(true);
    setError(null);
    try {
      console.log('Making request to demo dashboard');
      const response = await axios.get(`${API}/demo/dashboard`);
      console.log('Demo dashboard response received:', response.status);
      console.log('Demo dashboard response data:', response.data);
      
      if (response.data) {
        console.log('About to set dashboard data:', response.data);
        setDashboardData(response.data);
        setLastSyncTime(new Date());
        console.log('Dashboard data set, current state should update');
      } else {
        console.error('No data in response');
        setError('No data received from server');
      }
    } catch (error) {
      console.error('Dashboard error details:', error);
      setError(`API Error: ${error.message || 'Failed to load dashboard'}`);
    } finally {
      console.log('Setting loading to false in finally block');
      setLoading(false);
    }
  };

  const syncStockData = async (isAutoSync = false) => {
    if (!isAutoSync) setLoading(true); // Don't show loading for auto-sync
    setError(null);
    try {
      console.log(`${isAutoSync ? 'Auto-syncing' : 'Manual syncing'} stock data, isDemoMode:`, isDemoMode);
      let syncResponse;
      if (isDemoMode) {
        // Use demo sync in demo mode
        console.log('Making sync request to:', `${API}/demo/sync`);
        syncResponse = await axios.post(`${API}/demo/sync`);
        console.log('Demo sync response:', syncResponse.data);
      } else {
        // Use authenticated sync
        syncResponse = await axios.post(`${API}/stocks/sync`);
      }
      
      // Refresh dashboard after sync
      await fetchDashboard();
      
      if (!isAutoSync) {
        // Show success message only for manual sync
        setError(`✅ Sync completed! Loaded ${syncResponse.data.count} stock entries`);
        setTimeout(() => setError(null), 3000);
      }
      
    } catch (error) {
      console.error('Sync error:', error);
      if (!isAutoSync) {
        setError('Failed to sync stock data: ' + (error.message || 'Unknown error'));
      }
    } finally {
      if (!isAutoSync) setLoading(false);
    }
  };

  // Auto-sync functionality
  const startAutoSync = () => {
    if (autoSyncInterval.current) return; // Already running
    
    console.log('Starting auto-sync every 30 seconds');
    autoSyncInterval.current = setInterval(() => {
      console.log('Auto-sync triggered');
      syncStockData(true); // Pass true to indicate auto-sync
    }, 30000); // 30 seconds
  };

  const stopAutoSync = () => {
    if (autoSyncInterval.current) {
      console.log('Stopping auto-sync');
      clearInterval(autoSyncInterval.current);
      autoSyncInterval.current = null;
    }
  };

  const toggleAutoSync = () => {
    if (autoSyncEnabled) {
      stopAutoSync();
      setAutoSyncEnabled(false);
    } else {
      startAutoSync();
      setAutoSyncEnabled(true);
    }
  };

  useEffect(() => {
    if (!hasInitialized.current) {
      console.log('useEffect triggered FIRST TIME, calling fetchDashboard and starting auto-sync');
      hasInitialized.current = true;
      fetchDashboard();
      
      // Start auto-sync after initial load
      if (autoSyncEnabled) {
        startAutoSync();
      }
    } else {
      console.log('useEffect triggered AGAIN, but skipping to prevent duplicates');
    }

    // Cleanup function to stop auto-sync when component unmounts
    return () => {
      stopAutoSync();
    };
  }, []); // Empty dependency array to run only once

  // Effect to handle auto-sync enable/disable
  useEffect(() => {
    if (autoSyncEnabled && hasInitialized.current) {
      startAutoSync();
    } else {
      stopAutoSync();
    }
  }, [autoSyncEnabled]);

  if (false) { // Temporarily disable loading screen for debugging
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading Market Pulse Dashboard...</p>
            {isDemoMode && <p className="text-blue-600 text-sm mt-2">Demo Mode</p>}
          </div>
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
        {isDemoMode && (
          <Alert className="mb-6 border-blue-200 bg-blue-50">
            <AlertDescription className="text-blue-700">
              🎯 Demo Mode: You're viewing sample stock data. <a href="/" className="underline font-medium">Sign in with Google</a> to connect your own Google Sheets.
            </AlertDescription>
          </Alert>
        )}
        
        {/* Debug info */}
        <div className="mb-4 p-2 bg-gray-100 text-xs">
          <p>Loading: {loading.toString()}</p>
          <p>Dashboard Data: {dashboardData ? 'Present' : 'Null'}</p>
          <p>Error: {error || 'None'}</p>
          <p>Total Stocks: {dashboardData?.total_stocks || 'N/A'}</p>
          <p>Recent Activity: {dashboardData?.latest_hour_stocks?.length || 'N/A'}</p>
          <p>Max Appearances: {dashboardData?.max_appearances_stocks?.length || 'N/A'}</p>
          <p>Recent Positive: {dashboardData?.recent_positive_stocks?.length || 'N/A'}</p>
        </div>
        
        {error && (
          <Alert className={`mb-6 ${error.includes('✅') ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
            <AlertDescription className={error.includes('✅') ? 'text-green-700' : 'text-red-700'}>{error}</AlertDescription>
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
              onRefresh={() => syncStockData(false)}
              loading={loading}
              autoSyncEnabled={autoSyncEnabled}
              toggleAutoSync={toggleAutoSync}
              lastSyncTime={lastSyncTime}
            />

            <div className="grid gap-6 lg:grid-cols-4">
              <StockList 
                title="🕐 Latest Activity (Last Hour)" 
                stocks={dashboardData?.latest_hour_stocks} 
                type="recent"
              />
              <StockList 
                title="📊 Maximum Appearances" 
                stocks={dashboardData?.max_appearances_stocks} 
                type="frequent"
              />
              <StockList 
                title="📈 Recent Positive (15min)" 
                stocks={dashboardData?.recent_positive_stocks} 
                type="positive"
              />
              <StockList 
                title="📉 Recent Declines (15min)" 
                stocks={dashboardData?.recent_negative_stocks} 
                type="negative"
              />
            </div>
          </TabsContent>

          <TabsContent value="analysis" className="space-y-6">
            <Card className="bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-200">
              <CardHeader>
                <CardTitle className="text-xl">🎯 Option Trading Analysis</CardTitle>
                <CardDescription>
                  AI-powered insights for option trading opportunities
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dashboardData?.ai_market_insights ? (
                  <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                    {dashboardData.ai_market_insights}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    Sync data to view option trading analysis
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

        <div className="space-y-4">
          <Button 
            onClick={login}
            size="lg"
            className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white px-8 py-4 text-lg font-semibold shadow-2xl"
            data-testid="get-started-btn"
          >
            Get Started with Google
          </Button>
          
          <div className="text-center">
            <p className="text-gray-400 text-xs mb-2">Or try the demo</p>
            <Button 
              onClick={() => window.location.href = '/dashboard?demo=true'}
              variant="outline"
              size="lg"
              className="border-white/20 text-white hover:bg-white/10 px-6 py-3"
              data-testid="demo-btn"
            >
              📊 View Demo Dashboard
            </Button>
          </div>
        </div>
        
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
  const isDemoMode = useMemo(() => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('demo') === 'true';
  }, []);

  if (loading && !isDemoMode) {
    return <LoadingScreen />;
  }

  if (!user && !isDemoMode) {
    return <LandingPage />;
  }

  return <Dashboard />;
};

export default App;