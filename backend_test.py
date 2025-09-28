import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class StockAnalysisAPITester:
    def __init__(self, base_url="https://market-pulse-267.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            "test_name": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Dict[Any, Any] = None, headers: Dict[str, str] = None) -> tuple:
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        # Default headers
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)
        
        # Add session token if available
        if self.session_token:
            test_headers['Authorization'] = f'Bearer {self.session_token}'

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        print(f"   Method: {method}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                self.log_test(name, True)
                try:
                    return True, response.json()
                except:
                    return True, {"message": "Success - No JSON response"}
            else:
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text[:200]}"
                
                self.log_test(name, False, error_msg)
                return False, {}

        except requests.exceptions.Timeout:
            self.log_test(name, False, "Request timeout (30s)")
            return False, {}
        except requests.exceptions.ConnectionError:
            self.log_test(name, False, "Connection error - service may be down")
            return False, {}
        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "/", 200)

    def test_auth_session_without_token(self):
        """Test session creation without token (should fail)"""
        return self.run_test("Auth Session (No Token)", "POST", "/auth/session", 400)

    def test_auth_me_unauthenticated(self):
        """Test getting user info without authentication"""
        return self.run_test("Get User Info (Unauthenticated)", "GET", "/auth/me", 401)

    def test_stocks_dashboard_unauthenticated(self):
        """Test dashboard access without authentication"""
        return self.run_test("Dashboard (Unauthenticated)", "GET", "/stocks/dashboard", 401)

    def test_stocks_sync_unauthenticated(self):
        """Test stock sync without authentication"""
        return self.run_test("Stock Sync (Unauthenticated)", "POST", "/stocks/sync", 401)

    def test_stocks_filters_unauthenticated(self):
        """Test stock filters without authentication"""
        return self.run_test("Stock Filters (Unauthenticated)", "GET", "/stocks/filters", 401)

    def test_stock_analysis_unauthenticated(self):
        """Test individual stock analysis without authentication"""
        return self.run_test("Stock Analysis (Unauthenticated)", "GET", "/stocks/analysis/NETWEB", 401)

    def test_google_sheets_auth_unauthenticated(self):
        """Test Google Sheets auth without authentication"""
        return self.run_test("Google Sheets Auth (Unauthenticated)", "POST", "/auth/google-sheets", 401)

    def test_logout_unauthenticated(self):
        """Test logout without authentication"""
        return self.run_test("Logout (Unauthenticated)", "POST", "/auth/logout", 401)

    def simulate_authenticated_session(self):
        """Simulate an authenticated session for testing protected endpoints"""
        print("\n🔐 Simulating authenticated session...")
        # For testing purposes, we'll create a mock session token
        # In real testing, this would come from the actual auth flow
        self.session_token = "mock_session_token_for_testing"
        print("   Mock session token created for protected endpoint testing")

    def test_with_mock_auth(self):
        """Test endpoints that require authentication with mock token"""
        self.simulate_authenticated_session()
        
        # These will likely fail with 401 since we're using a mock token
        # but we can test the endpoint structure
        
        success, _ = self.run_test("Dashboard (Mock Auth)", "GET", "/stocks/dashboard", 401)
        success, _ = self.run_test("Stock Sync (Mock Auth)", "POST", "/stocks/sync", 401)
        success, _ = self.run_test("Stock Filters (Mock Auth)", "GET", "/stocks/filters", 401)
        success, _ = self.run_test("Stock Analysis (Mock Auth)", "GET", "/stocks/analysis/NETWEB", 401)
        success, _ = self.run_test("Google Sheets Auth (Mock Auth)", "POST", "/auth/google-sheets", 401)

    def test_cors_headers(self):
        """Test CORS configuration"""
        print("\n🌐 Testing CORS headers...")
        try:
            response = requests.options(f"{self.api_url}/", timeout=10)
            cors_headers = {
                'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
            }
            
            print(f"   CORS Headers: {cors_headers}")
            
            # Check if CORS is properly configured
            if cors_headers['Access-Control-Allow-Origin']:
                self.log_test("CORS Configuration", True, "CORS headers present")
            else:
                self.log_test("CORS Configuration", False, "Missing CORS headers")
                
        except Exception as e:
            self.log_test("CORS Configuration", False, f"CORS test failed: {str(e)}")

    def test_api_structure(self):
        """Test API endpoint structure and responses"""
        print("\n📋 Testing API Structure...")
        
        # Test various endpoints for proper error handling
        endpoints_to_test = [
            ("/nonexistent", 404),
            ("/auth/invalid", 404),
            ("/stocks/invalid", 404),
        ]
        
        for endpoint, expected_status in endpoints_to_test:
            self.run_test(f"Invalid Endpoint {endpoint}", "GET", endpoint, expected_status)

    def run_comprehensive_test(self):
        """Run all tests"""
        print("🚀 Starting Stock Analysis API Comprehensive Test")
        print(f"   Base URL: {self.base_url}")
        print(f"   API URL: {self.api_url}")
        print("=" * 60)

        # Test basic connectivity
        self.test_root_endpoint()
        
        # Test CORS
        self.test_cors_headers()
        
        # Test unauthenticated access (should be properly blocked)
        self.test_auth_me_unauthenticated()
        self.test_stocks_dashboard_unauthenticated()
        self.test_stocks_sync_unauthenticated()
        self.test_stocks_filters_unauthenticated()
        self.test_stock_analysis_unauthenticated()
        self.test_google_sheets_auth_unauthenticated()
        self.test_logout_unauthenticated()
        
        # Test auth endpoints
        self.test_auth_session_without_token()
        
        # Test with mock authentication
        self.test_with_mock_auth()
        
        # Test API structure
        self.test_api_structure()

        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        # Detailed results
        print("\n📋 DETAILED RESULTS:")
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test_name']}")
            if not result["success"] and result["details"]:
                print(f"   └─ {result['details']}")

        return self.tests_passed == self.tests_run

def main():
    """Main test function"""
    tester = StockAnalysisAPITester()
    
    try:
        success = tester.run_comprehensive_test()
        
        # Save results to file
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": tester.tests_run,
            "passed_tests": tester.tests_passed,
            "failed_tests": tester.tests_run - tester.tests_passed,
            "success_rate": (tester.tests_passed/tester.tests_run)*100 if tester.tests_run > 0 else 0,
            "test_details": tester.test_results
        }
        
        with open('/app/backend_test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Results saved to /app/backend_test_results.json")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n💥 Test suite failed with error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())