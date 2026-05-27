/**
 * Authentication module
 * Handles login, register, logout, and auth checks
 */

const API_BASE = '/';

/**
 * Register a new account
 */
async function register(data) {
    const response = await fetch(`${API_BASE}auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            email: data.email,
            password: data.password,
            full_name: data.fullName,
        }),
    });
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Registration failed');
    }
    
    return await response.json();
}

/**
 * Login with email and password
 */
async function login(email, password) {
    const formData = new FormData();
    formData.append('username', email);  // fastapi-users expects 'username' field
    formData.append('password', password);
    
    const response = await fetch(`${API_BASE}auth/jwt/login`, {
        method: 'POST',
        body: formData,
    });
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
    }
    
    const data = await response.json();
    
    // Store token in localStorage
    if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
    }
    
    return data;
}

/**
 * Logout user
 */
async function logout() {
    try {
        await fetch(`${API_BASE}auth/jwt/logout`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            },
        });
    } catch (e) {
        console.error('Logout error:', e);
    }
    
    // Clear token
    localStorage.removeItem('access_token');
    
    // Redirect to login
    window.location.href = 'login.html';
}

/**
 * Check if user is authenticated and get current user info
 * Throws if not authenticated
 */
async function checkAuth() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        throw new Error('Not authenticated');
    }
    
    const response = await fetch(`${API_BASE}users/me`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`,
        },
    });
    
    if (!response.ok) {
        localStorage.removeItem('access_token');
        throw new Error('Not authenticated');
    }
    
    return await response.json();
}

/**
 * Get current user or null if not authenticated
 */
async function getCurrentUser() {
    try {
        return await checkAuth();
    } catch (e) {
        return null;
    }
}

/**
 * Make an authenticated API request
 */
async function apiRequest(endpoint, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
    });
    
    if (response.status === 401) {
        localStorage.removeItem('access_token');
        window.location.href = 'login.html';
        throw new Error('Unauthorized');
    }
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'API request failed');
    }
    
    return await response.json();
}

/**
 * Get auth token from localStorage
 */
function getToken() {
    return localStorage.getItem('access_token');
}

// ---------------------------------------------------------------
// Expose as globals so login.html / register.html inline scripts
// can call these when auth.js is loaded as a classic <script src>
// ---------------------------------------------------------------
window.login = login;
window.logout = logout;
window.register = register;
window.checkAuth = checkAuth;
window.getCurrentUser = getCurrentUser;
window.apiRequest = apiRequest;
window.getToken = getToken;
