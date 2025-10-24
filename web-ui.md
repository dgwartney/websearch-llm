# Password-Protected Web UI for WebSearch LLM

This document describes the architecture and implementation approach for a password-protected static website that provides a user interface for querying the websearch-llm Lambda function.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Solution 1: Amazon Cognito Authentication (Recommended)](#solution-1-amazon-cognito-authentication-recommended)
3. [Solution 2: AWS Amplify](#solution-2-aws-amplify-simplified-alternative)
4. [Solution 3: Basic Authentication](#solution-3-simple-password-protection-basic-auth)
5. [Security Considerations](#security-considerations)
6. [Cost Estimation](#cost-estimation)
7. [Deployment Process](#deployment-process)
8. [Advanced Features](#advanced-features)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Browser                              │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Static Website (S3 + CloudFront)                      │    │
│  │  - HTML/CSS/JavaScript                                 │    │
│  │  - Login Form                                          │    │
│  │  - Query Interface                                     │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         │ 1. Authenticate              │ 3. API Call with JWT
         ▼                              ▼
┌──────────────────────┐      ┌──────────────────────────┐
│   Amazon Cognito     │      │   API Gateway            │
│   User Pool          │      │   (with Cognito Auth)    │
│   - Username/Password│      │   - JWT Validation       │
│   - JWT Tokens       │      │   - Rate Limiting        │
└──────────────────────┘      └──────────────────────────┘
         │                              │
         │ 2. Return JWT                │ 4. Invoke
         │                              ▼
         │                    ┌──────────────────────────┐
         │                    │   Lambda Function        │
         │                    │   (websearch-llm)        │
         │                    │   - Search & LLM         │
         │                    └──────────────────────────┘
         │                              │
         │                              │ 5. Return Results
         │                              ▼
         └──────────────────────────────────────────────────
                           6. Display Results
```

---

## Solution 1: Amazon Cognito Authentication (Recommended)

### Components

#### 1. Amazon Cognito User Pool

**Purpose:** Manages user authentication, password policies, and JWT token generation.

**CloudFormation Configuration:**
```yaml
CognitoUserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: websearch-llm-users
    AutoVerifiedAttributes:
      - email
    Policies:
      PasswordPolicy:
        MinimumLength: 8
        RequireUppercase: true
        RequireLowercase: true
        RequireNumbers: true
        RequireSymbols: true
    MfaConfiguration: OPTIONAL
    AccountRecoverySetting:
      RecoveryMechanisms:
        - Name: verified_email
          Priority: 1
    UserAttributeUpdateSettings:
      AttributesRequireVerificationBeforeUpdate:
        - email

CognitoUserPoolClient:
  Type: AWS::Cognito::UserPoolClient
  Properties:
    ClientName: websearch-llm-web-client
    UserPoolId: !Ref CognitoUserPool
    ExplicitAuthFlows:
      - ALLOW_USER_PASSWORD_AUTH
      - ALLOW_REFRESH_TOKEN_AUTH
    TokenValidityUnits:
      AccessToken: hours
      IdToken: hours
      RefreshToken: days
    AccessTokenValidity: 1
    IdTokenValidity: 1
    RefreshTokenValidity: 30
    PreventUserExistenceErrors: ENABLED
```

**User Creation Options:**
- Admin creates users via AWS Console
- Self-registration with email verification (optional)
- Import users from CSV
- Federate with corporate identity provider (SAML/OIDC)

**Key Features:**
- Password complexity enforcement
- Account recovery via email
- Optional Multi-Factor Authentication (MFA)
- Token expiration and refresh
- User attribute verification

#### 2. API Gateway Authorizer

Update your existing API Gateway to use Cognito authorization instead of x-api-key.

**Template Updates (template.yaml):**
```yaml
WebSearchApi:
  Type: AWS::Serverless::Api
  Properties:
    StageName: prod
    Auth:
      DefaultAuthorizer: CognitoAuthorizer
      Authorizers:
        CognitoAuthorizer:
          UserPoolArn: !GetAtt CognitoUserPool.Arn
          Identity:
            Header: Authorization
      ApiKeyRequired: false  # Replace x-api-key with Cognito
    Cors:
      AllowMethods: "'POST, OPTIONS'"
      AllowHeaders: "'Content-Type,Authorization'"
      AllowOrigin: "'https://your-domain.com'"
    TracingEnabled: true
```

**How it works:**
1. Client includes JWT in `Authorization: Bearer <token>` header
2. API Gateway validates JWT signature against Cognito User Pool
3. If valid, request proceeds to Lambda with user context
4. If invalid, returns 401 Unauthorized with WWW-Authenticate header

**Benefits:**
- No need to manage API keys manually
- Per-user authentication and authorization
- Automatic token validation
- User identity passed to Lambda in `event.requestContext.authorizer.claims`

#### 3. Static Website Hosting (S3 + CloudFront)

**CloudFormation Resources:**
```yaml
# S3 Bucket (Private)
WebsiteBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: websearch-llm-frontend
    PublicAccessBlockConfiguration:
      BlockPublicAcls: true
      BlockPublicPolicy: true
      IgnorePublicAcls: true
      RestrictPublicBuckets: true
    WebsiteConfiguration:
      IndexDocument: index.html
      ErrorDocument: error.html
    VersioningConfiguration:
      Status: Enabled
    Tags:
      - Key: Purpose
        Value: Static Website Hosting

# CloudFront Origin Access Identity
CloudFrontOAI:
  Type: AWS::CloudFront::CloudFrontOriginAccessIdentity
  Properties:
    CloudFrontOriginAccessIdentityConfig:
      Comment: OAI for websearch-llm frontend

# Bucket Policy (Allow CloudFront OAI)
WebsiteBucketPolicy:
  Type: AWS::S3::BucketPolicy
  Properties:
    Bucket: !Ref WebsiteBucket
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            CanonicalUser: !GetAtt CloudFrontOAI.S3CanonicalUserId
          Action: s3:GetObject
          Resource: !Sub '${WebsiteBucket.Arn}/*'

# CloudFront Distribution
CloudFrontDistribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    DistributionConfig:
      Enabled: true
      DefaultRootObject: index.html
      Comment: WebSearch LLM Frontend
      Origins:
        - Id: S3Origin
          DomainName: !GetAtt WebsiteBucket.RegionalDomainName
          S3OriginConfig:
            OriginAccessIdentity: !Sub 'origin-access-identity/cloudfront/${CloudFrontOAI}'
      DefaultCacheBehavior:
        TargetOriginId: S3Origin
        ViewerProtocolPolicy: redirect-to-https
        AllowedMethods: [GET, HEAD, OPTIONS]
        CachedMethods: [GET, HEAD]
        Compress: true
        ForwardedValues:
          QueryString: false
          Cookies:
            Forward: none
        MinTTL: 0
        DefaultTTL: 86400
        MaxTTL: 31536000
      CustomErrorResponses:
        - ErrorCode: 404
          ResponseCode: 200
          ResponsePagePath: /index.html
        - ErrorCode: 403
          ResponseCode: 200
          ResponsePagePath: /index.html
      ViewerCertificate:
        CloudFrontDefaultCertificate: true
        # For custom domain with SSL:
        # AcmCertificateArn: !Ref SSLCertificate
        # SslSupportMethod: sni-only
        # MinimumProtocolVersion: TLSv1.2_2021
      HttpVersion: http2
      IPV6Enabled: true
```

**Security Features:**
- S3 bucket is private (not publicly accessible)
- CloudFront uses Origin Access Identity (OAI) to access S3
- HTTPS enforced via CloudFront
- Versioning enabled for rollback capability
- Optional: Custom domain with ACM SSL certificate
- Optional: WAF integration for additional protection

#### 4. Frontend Code Structure

```
frontend/
├── index.html              # Login page
├── app.html               # Main application (query interface)
├── css/
│   ├── styles.css         # Main application styles
│   └── login.css          # Login page styles
├── js/
│   ├── config.js          # AWS configuration
│   ├── auth.js            # Cognito authentication logic
│   ├── api.js             # Lambda API client
│   └── app.js             # Main application logic
├── assets/
│   ├── logo.png           # Branding
│   └── favicon.ico        # Browser icon
└── error.html             # Error page
```

#### 5. Authentication Flow (JavaScript)

**config.js:**
```javascript
const config = {
    cognito: {
        userPoolId: 'us-east-1_XXXXXXXXX',
        clientId: 'xxxxxxxxxxxxxxxxxxxxxxxxxx',
        region: 'us-east-1'
    },
    api: {
        endpoint: 'https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/search'
    }
};

export { config };
```

**auth.js:**
```javascript
// Uses Amazon Cognito Identity SDK for JavaScript
// https://github.com/aws-amplify/amplify-js

import { CognitoUserPool, CognitoUser, AuthenticationDetails } from 'amazon-cognito-identity-js';

class AuthService {
    constructor(config) {
        this.userPool = new CognitoUserPool({
            UserPoolId: config.userPoolId,
            ClientId: config.clientId
        });
    }

    /**
     * Login with username and password
     * @param {string} username - User's username or email
     * @param {string} password - User's password
     * @returns {Promise<Object>} JWT tokens
     */
    async login(username, password) {
        const authenticationDetails = new AuthenticationDetails({
            Username: username,
            Password: password
        });

        const cognitoUser = new CognitoUser({
            Username: username,
            Pool: this.userPool
        });

        return new Promise((resolve, reject) => {
            cognitoUser.authenticateUser(authenticationDetails, {
                onSuccess: (result) => {
                    const idToken = result.getIdToken().getJwtToken();
                    const accessToken = result.getAccessToken().getJwtToken();
                    const refreshToken = result.getRefreshToken().getToken();

                    // Store tokens in sessionStorage (cleared on browser close)
                    // Use localStorage for "Remember Me" functionality
                    sessionStorage.setItem('idToken', idToken);
                    sessionStorage.setItem('accessToken', accessToken);
                    sessionStorage.setItem('refreshToken', refreshToken);
                    sessionStorage.setItem('username', username);

                    resolve({ idToken, accessToken, refreshToken });
                },
                onFailure: (err) => {
                    reject(err);
                },
                mfaRequired: (codeDeliveryDetails) => {
                    // Handle MFA if enabled
                    const verificationCode = prompt(`Enter MFA code sent to ${codeDeliveryDetails.CodeDeliveryDetails.Destination}:`);
                    if (verificationCode) {
                        cognitoUser.sendMFACode(verificationCode, this);
                    } else {
                        reject(new Error('MFA code required'));
                    }
                },
                newPasswordRequired: (userAttributes, requiredAttributes) => {
                    // Handle forced password change for new users
                    const newPassword = prompt('You must set a new password:');
                    if (newPassword) {
                        delete userAttributes.email_verified;
                        cognitoUser.completeNewPasswordChallenge(newPassword, userAttributes, this);
                    } else {
                        reject(new Error('New password required'));
                    }
                }
            });
        });
    }

    /**
     * Get current valid token (refresh if expired)
     * @returns {Promise<string>} Valid ID token
     */
    async getValidToken() {
        const idToken = sessionStorage.getItem('idToken');

        if (!idToken) {
            throw new Error('Not authenticated');
        }

        // Check if token is expired (JWT expiration is in payload)
        const payload = JSON.parse(atob(idToken.split('.')[1]));
        const expirationTime = payload.exp * 1000;

        // Refresh if expiring in less than 1 minute
        if (Date.now() >= expirationTime - 60000) {
            return await this.refreshToken();
        }

        return idToken;
    }

    /**
     * Refresh expired token
     * @returns {Promise<string>} New ID token
     */
    async refreshToken() {
        const cognitoUser = this.userPool.getCurrentUser();
        const refreshToken = sessionStorage.getItem('refreshToken');

        if (!cognitoUser || !refreshToken) {
            throw new Error('Cannot refresh token - not authenticated');
        }

        return new Promise((resolve, reject) => {
            cognitoUser.refreshSession(new CognitoRefreshToken({ RefreshToken: refreshToken }), (err, session) => {
                if (err) {
                    this.logout();
                    reject(err);
                } else {
                    const idToken = session.getIdToken().getJwtToken();
                    const accessToken = session.getAccessToken().getJwtToken();
                    sessionStorage.setItem('idToken', idToken);
                    sessionStorage.setItem('accessToken', accessToken);
                    resolve(idToken);
                }
            });
        });
    }

    /**
     * Logout user and clear session
     */
    logout() {
        const cognitoUser = this.userPool.getCurrentUser();
        if (cognitoUser) {
            cognitoUser.signOut();
        }
        sessionStorage.clear();
        window.location.href = '/index.html';
    }

    /**
     * Check if user is authenticated
     * @returns {boolean} Authentication status
     */
    isAuthenticated() {
        const idToken = sessionStorage.getItem('idToken');
        if (!idToken) return false;

        try {
            const payload = JSON.parse(atob(idToken.split('.')[1]));
            return Date.now() < payload.exp * 1000;
        } catch {
            return false;
        }
    }

    /**
     * Get current username
     * @returns {string|null} Username or null if not authenticated
     */
    getUsername() {
        return sessionStorage.getItem('username');
    }

    /**
     * Change password
     * @param {string} oldPassword - Current password
     * @param {string} newPassword - New password
     * @returns {Promise<void>}
     */
    async changePassword(oldPassword, newPassword) {
        const cognitoUser = this.userPool.getCurrentUser();

        return new Promise((resolve, reject) => {
            cognitoUser.getSession((err, session) => {
                if (err) {
                    reject(err);
                    return;
                }

                cognitoUser.changePassword(oldPassword, newPassword, (err, result) => {
                    if (err) {
                        reject(err);
                    } else {
                        resolve(result);
                    }
                });
            });
        });
    }

    /**
     * Request password reset
     * @param {string} username - Username for password reset
     * @returns {Promise<Object>} Code delivery details
     */
    async forgotPassword(username) {
        const cognitoUser = new CognitoUser({
            Username: username,
            Pool: this.userPool
        });

        return new Promise((resolve, reject) => {
            cognitoUser.forgotPassword({
                onSuccess: (data) => resolve(data),
                onFailure: (err) => reject(err)
            });
        });
    }

    /**
     * Confirm password reset with verification code
     * @param {string} username - Username
     * @param {string} verificationCode - Code sent to user's email
     * @param {string} newPassword - New password
     * @returns {Promise<void>}
     */
    async confirmPassword(username, verificationCode, newPassword) {
        const cognitoUser = new CognitoUser({
            Username: username,
            Pool: this.userPool
        });

        return new Promise((resolve, reject) => {
            cognitoUser.confirmPassword(verificationCode, newPassword, {
                onSuccess: () => resolve(),
                onFailure: (err) => reject(err)
            });
        });
    }
}

export { AuthService };
```

**api.js:**
```javascript
class LambdaClient {
    constructor(apiEndpoint, authService) {
        this.apiEndpoint = apiEndpoint;
        this.authService = authService;
    }

    /**
     * Query the Lambda function with user input
     * @param {string} userQuery - Search query
     * @param {number} maxResults - Maximum URLs to search (1-20)
     * @param {number} maxChunks - Maximum chunks to use (1-50)
     * @returns {Promise<Object>} Search results
     */
    async query(userQuery, maxResults = 5, maxChunks = 10) {
        try {
            // Get valid JWT token (will refresh if needed)
            const token = await this.authService.getValidToken();

            // Call Lambda via API Gateway
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    query: userQuery,
                    max_results: maxResults,
                    max_chunks: maxChunks
                })
            });

            if (!response.ok) {
                if (response.status === 401 || response.status === 403) {
                    // Token invalid or expired, redirect to login
                    this.authService.logout();
                    throw new Error('Authentication expired - please login again');
                }

                const errorBody = await response.json().catch(() => ({}));
                throw new Error(errorBody.error || `API error: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            console.error('Query failed:', error);
            throw error;
        }
    }

    /**
     * Validate query before sending
     * @param {string} query - Query to validate
     * @throws {Error} If query is invalid
     */
    validateQuery(query) {
        if (!query || query.trim().length === 0) {
            throw new Error('Query cannot be empty');
        }
        if (query.length > 500) {
            throw new Error('Query too long (max 500 characters)');
        }
        // Allow alphanumeric, spaces, and common punctuation
        if (!/^[\w\s\?\.,!'\"-]+$/u.test(query)) {
            throw new Error('Query contains invalid characters');
        }
    }
}

export { LambdaClient };
```

**app.js:**
```javascript
import { AuthService } from './auth.js';
import { LambdaClient } from './api.js';
import { config } from './config.js';

// Initialize services
const authService = new AuthService(config.cognito);
const lambdaClient = new LambdaClient(config.api.endpoint, authService);

// Check authentication on page load
window.addEventListener('DOMContentLoaded', () => {
    if (!authService.isAuthenticated()) {
        window.location.href = '/index.html';
        return;
    }

    // Display username
    const username = authService.getUsername();
    document.getElementById('username').textContent = username;

    // Setup event listeners
    setupEventListeners();
});

function setupEventListeners() {
    // Query form submission
    const queryForm = document.getElementById('queryForm');
    queryForm.addEventListener('submit', handleQuerySubmit);

    // Logout button
    const logoutBtn = document.getElementById('logoutBtn');
    logoutBtn.addEventListener('click', () => authService.logout());

    // Enter key in textarea (Shift+Enter for new line, Enter to submit)
    const queryInput = document.getElementById('queryInput');
    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            queryForm.dispatchEvent(new Event('submit'));
        }
    });

    // Clear button
    const clearBtn = document.getElementById('clearBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            document.getElementById('queryInput').value = '';
            document.getElementById('results').innerHTML = '';
        });
    }
}

async function handleQuerySubmit(event) {
    event.preventDefault();

    const query = document.getElementById('queryInput').value.trim();
    const maxResults = parseInt(document.getElementById('maxResults').value) || 5;
    const maxChunks = parseInt(document.getElementById('maxChunks').value) || 10;
    const resultsDiv = document.getElementById('results');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');

    // Validate query
    try {
        lambdaClient.validateQuery(query);
    } catch (error) {
        showError(error.message);
        return;
    }

    // Show loading state
    loadingDiv.style.display = 'block';
    resultsDiv.innerHTML = '';
    errorDiv.style.display = 'none';

    const startTime = performance.now();

    try {
        // Call Lambda function
        const result = await lambdaClient.query(query, maxResults, maxChunks);

        const endTime = performance.now();
        const clientTime = Math.round(endTime - startTime);

        // Display results
        displayResults(result, clientTime);

    } catch (error) {
        showError(error.message);
    } finally {
        loadingDiv.style.display = 'none';
    }
}

function displayResults(data, clientTime) {
    const resultsDiv = document.getElementById('results');

    // Display answer
    const answerHtml = `
        <div class="answer-card">
            <h2>Answer</h2>
            <div class="answer-text">${formatText(data.answer)}</div>
        </div>
    `;

    // Display sources with similarity scores
    const sourcesHtml = `
        <div class="sources-card">
            <h3>Sources (${data.source_details.length})</h3>
            <div class="source-list">
                ${data.source_details.map(source => `
                    <div class="source-item">
                        <div class="source-header">
                            <span class="source-rank">Rank ${source.rank}</span>
                            <span class="source-score">
                                <span class="score-bar" style="width: ${source.similarity_score * 100}%"></span>
                                ${(source.similarity_score * 100).toFixed(1)}% relevance
                            </span>
                        </div>
                        <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" class="source-url">
                            ${escapeHtml(source.url)}
                        </a>
                        <p class="source-preview">${escapeHtml(source.content_preview)}</p>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // Display metadata
    const metadataHtml = `
        <div class="metadata-card">
            <div class="metadata-grid">
                <div class="metadata-item">
                    <span class="metadata-label">Chunks Processed:</span>
                    <span class="metadata-value">${data.metadata.chunks_processed}</span>
                </div>
                <div class="metadata-item">
                    <span class="metadata-label">URLs Scraped:</span>
                    <span class="metadata-value">${data.metadata.urls_scraped}</span>
                </div>
                <div class="metadata-item">
                    <span class="metadata-label">Server Time:</span>
                    <span class="metadata-value">${data.metadata.total_time_ms}ms</span>
                </div>
                <div class="metadata-item">
                    <span class="metadata-label">Total Time:</span>
                    <span class="metadata-value">${clientTime}ms</span>
                </div>
            </div>
        </div>
    `;

    resultsDiv.innerHTML = answerHtml + sourcesHtml + metadataHtml;
    resultsDiv.style.display = 'block';
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatText(text) {
    // Convert newlines to <br>, preserve formatting
    return escapeHtml(text).replace(/\n/g, '<br>');
}
```

#### 6. HTML Pages

**index.html (Login Page):**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self';
                   script-src 'self' 'unsafe-inline' https://sdk.amazonaws.com;
                   connect-src 'self' https://*.amazonaws.com;
                   style-src 'self' 'unsafe-inline';
                   img-src 'self' data:;">
    <title>WestJet Knowledge Search - Login</title>
    <link rel="stylesheet" href="css/login.css">
    <link rel="icon" type="image/x-icon" href="assets/favicon.ico">
</head>
<body>
    <div class="login-container">
        <div class="login-card">
            <div class="login-header">
                <img src="assets/logo.png" alt="WestJet Logo" class="logo">
                <h1>Knowledge Search</h1>
                <p class="subtitle">Sign in to access the search portal</p>
            </div>

            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username or Email</label>
                    <input
                        type="text"
                        id="username"
                        required
                        autocomplete="username"
                        placeholder="Enter your username"
                        autofocus
                    >
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input
                        type="password"
                        id="password"
                        required
                        autocomplete="current-password"
                        placeholder="Enter your password"
                    >
                </div>

                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="rememberMe">
                        <span>Remember me</span>
                    </label>
                </div>

                <button type="submit" class="btn-primary">Sign In</button>

                <div id="error" class="error-message" style="display: none;"></div>
            </form>

            <div class="login-footer">
                <a href="#" id="forgotPassword">Forgot password?</a>
            </div>
        </div>
    </div>

    <script type="module" src="js/config.js"></script>
    <script type="module" src="js/auth.js"></script>
    <script type="module">
        import { AuthService } from './js/auth.js';
        import { config } from './js/config.js';

        const authService = new AuthService(config.cognito);

        // Check if already authenticated
        if (authService.isAuthenticated()) {
            window.location.href = '/app.html';
        }

        // Handle login form submission
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;
            const rememberMe = document.getElementById('rememberMe').checked;
            const errorDiv = document.getElementById('error');
            const submitBtn = e.target.querySelector('button[type="submit"]');

            // Show loading state
            submitBtn.disabled = true;
            submitBtn.textContent = 'Signing in...';
            errorDiv.style.display = 'none';

            try {
                await authService.login(username, password);

                // If remember me, copy to localStorage
                if (rememberMe) {
                    localStorage.setItem('idToken', sessionStorage.getItem('idToken'));
                    localStorage.setItem('accessToken', sessionStorage.getItem('accessToken'));
                    localStorage.setItem('refreshToken', sessionStorage.getItem('refreshToken'));
                    localStorage.setItem('username', username);
                }

                window.location.href = '/app.html';
            } catch (error) {
                errorDiv.textContent = error.message || 'Login failed. Please check your credentials.';
                errorDiv.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Sign In';
            }
        });

        // Handle forgot password
        document.getElementById('forgotPassword').addEventListener('click', async (e) => {
            e.preventDefault();

            const username = prompt('Enter your username or email:');
            if (!username) return;

            try {
                await authService.forgotPassword(username);
                alert(`Password reset instructions sent to your email. Check your inbox.`);
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        });
    </script>
</body>
</html>
```

**app.html (Query Interface):**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self';
                   script-src 'self' 'unsafe-inline' https://sdk.amazonaws.com;
                   connect-src 'self' https://*.amazonaws.com;
                   style-src 'self' 'unsafe-inline';
                   img-src 'self' data:;">
    <title>WestJet Knowledge Search</title>
    <link rel="stylesheet" href="css/styles.css">
    <link rel="icon" type="image/x-icon" href="assets/favicon.ico">
</head>
<body>
    <header class="header">
        <nav class="navbar">
            <div class="nav-brand">
                <img src="assets/logo.png" alt="WestJet Logo" class="logo-small">
                <h1>Knowledge Search</h1>
            </div>
            <div class="nav-user">
                <span class="username-display">
                    Welcome, <strong id="username"></strong>
                </span>
                <button id="logoutBtn" class="btn-secondary">Logout</button>
            </div>
        </nav>
    </header>

    <main class="main-content">
        <div class="search-container">
            <form id="queryForm" class="search-form">
                <div class="search-box">
                    <textarea
                        id="queryInput"
                        placeholder="Ask a question about WestJet (e.g., What are the baggage fees?)"
                        required
                        autocomplete="off"
                        rows="3"
                    ></textarea>
                    <div class="search-actions">
                        <button type="submit" class="btn-primary">
                            <span class="btn-icon">🔍</span>
                            Search
                        </button>
                        <button type="button" id="clearBtn" class="btn-secondary">Clear</button>
                    </div>
                </div>

                <div class="search-options">
                    <div class="option-group">
                        <label for="maxResults">
                            Max URLs:
                            <input type="number" id="maxResults" value="5" min="1" max="20">
                        </label>
                    </div>
                    <div class="option-group">
                        <label for="maxChunks">
                            Max Chunks:
                            <input type="number" id="maxChunks" value="10" min="1" max="50">
                        </label>
                    </div>
                </div>
            </form>
        </div>

        <div id="error" class="error-banner" style="display: none;"></div>

        <div id="loading" class="loading-container" style="display: none;">
            <div class="spinner"></div>
            <p class="loading-text">Searching and analyzing content...</p>
            <p class="loading-subtext">This may take 4-10 seconds</p>
        </div>

        <div id="results" class="results-container" style="display: none;"></div>
    </main>

    <footer class="footer">
        <p>&copy; 2024 WestJet. Powered by AWS Lambda and Claude AI.</p>
    </footer>

    <script type="module" src="js/app.js"></script>
</body>
</html>
```

**error.html:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error - WestJet Knowledge Search</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <div class="error-page">
        <h1>Oops! Something went wrong</h1>
        <p>We're sorry, but the page you're looking for couldn't be found.</p>
        <a href="/index.html" class="btn-primary">Return to Login</a>
    </div>
</body>
</html>
```

#### 7. CSS Styling (Sample)

**login.css:**
```css
:root {
    --primary-color: #0066cc;
    --primary-hover: #0052a3;
    --error-color: #d32f2f;
    --background: #f5f5f5;
    --card-background: #ffffff;
    --text-primary: #333333;
    --text-secondary: #666666;
    --border-color: #e0e0e0;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: var(--background);
    color: var(--text-primary);
    line-height: 1.6;
}

.login-container {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
}

.login-card {
    background: var(--card-background);
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    padding: 40px;
    width: 100%;
    max-width: 400px;
}

.login-header {
    text-align: center;
    margin-bottom: 30px;
}

.logo {
    max-width: 120px;
    margin-bottom: 20px;
}

.login-header h1 {
    font-size: 24px;
    margin-bottom: 8px;
}

.subtitle {
    color: var(--text-secondary);
    font-size: 14px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
    font-size: 14px;
}

.form-group input[type="text"],
.form-group input[type="password"] {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 14px;
    transition: border-color 0.3s;
}

.form-group input:focus {
    outline: none;
    border-color: var(--primary-color);
}

.checkbox-label {
    display: flex;
    align-items: center;
    font-weight: normal;
}

.checkbox-label input {
    margin-right: 8px;
}

.btn-primary {
    width: 100%;
    padding: 12px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.3s;
}

.btn-primary:hover {
    background: var(--primary-hover);
}

.btn-primary:disabled {
    background: #cccccc;
    cursor: not-allowed;
}

.error-message {
    margin-top: 15px;
    padding: 12px;
    background: #ffebee;
    border: 1px solid var(--error-color);
    border-radius: 4px;
    color: var(--error-color);
    font-size: 14px;
}

.login-footer {
    margin-top: 20px;
    text-align: center;
}

.login-footer a {
    color: var(--primary-color);
    text-decoration: none;
    font-size: 14px;
}

.login-footer a:hover {
    text-decoration: underline;
}
```

---

## Solution 2: AWS Amplify (Simplified Alternative)

AWS Amplify provides a higher-level abstraction that handles authentication, hosting, and API calls automatically with less boilerplate code.

### Overview

Amplify is a complete framework that simplifies:
- User authentication (Cognito)
- Static hosting (S3 + CloudFront)
- API integration
- CI/CD deployment

### Setup Steps

**1. Install Amplify CLI:**
```bash
npm install -g @aws-amplify/cli
amplify configure
```

**2. Initialize Amplify in your project:**
```bash
mkdir websearch-frontend
cd websearch-frontend
npm init -y
npm install aws-amplify

amplify init
# Follow prompts to configure
```

**3. Add authentication:**
```bash
amplify add auth
# Choose default configuration
# Enable username and email sign-in
# Configure password requirements

amplify push
```

**4. Add hosting:**
```bash
amplify add hosting
# Choose: Hosting with Amplify Console
# Choose: Manual deployment

amplify publish
```

**5. Frontend Code (Simplified with Amplify):**

```javascript
import { Amplify, Auth, API } from 'aws-amplify';

// Auto-configure from amplify outputs
import awsconfig from './aws-exports';
Amplify.configure(awsconfig);

// Manually add your Lambda endpoint
Amplify.configure({
    ...awsconfig,
    API: {
        endpoints: [
            {
                name: 'websearch',
                endpoint: 'https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod',
                region: 'us-east-1'
            }
        ]
    }
});

// Login (much simpler)
async function login(username, password) {
    try {
        const user = await Auth.signIn(username, password);
        console.log('Login successful', user);
        return user;
    } catch (error) {
        console.error('Login failed', error);
        throw error;
    }
}

// Make authenticated API call (automatically includes JWT)
async function queryLambda(query) {
    try {
        const response = await API.post('websearch', '/search', {
            body: {
                query: query,
                max_results: 5,
                max_chunks: 10
            }
        });
        return response;
    } catch (error) {
        console.error('Query failed', error);
        throw error;
    }
}

// Logout
async function logout() {
    try {
        await Auth.signOut();
        console.log('Logged out successfully');
    } catch (error) {
        console.error('Logout failed', error);
    }
}

// Check authentication status
async function checkAuth() {
    try {
        const user = await Auth.currentAuthenticatedUser();
        return user;
    } catch {
        return null;
    }
}
```

### Amplify UI Components

Amplify provides pre-built UI components:

```javascript
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

function App() {
    return (
        <Authenticator>
            {({ signOut, user }) => (
                <div>
                    <h1>Welcome {user.username}</h1>
                    <button onClick={signOut}>Sign out</button>
                    <SearchInterface />
                </div>
            )}
        </Authenticator>
    );
}
```

### Pros and Cons

**Pros:**
- Much simpler to implement (less boilerplate)
- Automatic token refresh
- Built-in UI components available
- Integrated CI/CD with Amplify Console
- One-command deployment
- Automatic environment management

**Cons:**
- Less control over implementation details
- Larger JavaScript bundle size
- Tied to AWS Amplify ecosystem
- Amplify CLI can be opinionated
- May generate files you don't need

### When to Use Amplify

- Quick prototypes or MVPs
- Teams familiar with Amplify
- Want pre-built UI components
- Need rapid development
- Prefer convention over configuration

---

## Solution 3: Simple Password Protection (Basic Auth)

For a quick, simple solution without Cognito (not recommended for production).

### Lambda@Edge Function for Basic Auth

```javascript
// CloudFront Lambda@Edge function
// Attach to "Viewer Request" event
exports.handler = async (event) => {
    const request = event.Records[0].cf.request;
    const headers = request.headers;

    // Expected credentials (in production, use AWS Secrets Manager)
    const authUser = process.env.AUTH_USER || 'admin';
    const authPass = process.env.AUTH_PASS || 'ChangeMe123!';
    const authString = 'Basic ' + Buffer.from(authUser + ':' + authPass).toString('base64');

    // Check if Authorization header exists and matches
    if (typeof headers.authorization === 'undefined' ||
        headers.authorization[0].value !== authString) {
        return {
            status: '401',
            statusDescription: 'Unauthorized',
            headers: {
                'www-authenticate': [{
                    key: 'WWW-Authenticate',
                    value: 'Basic realm="WestJet Knowledge Search"'
                }],
                'content-type': [{
                    key: 'Content-Type',
                    value: 'text/html'
                }]
            },
            body: '<html><body><h1>401 Unauthorized</h1><p>Authentication required.</p></body></html>'
        };
    }

    // Authentication successful, pass request through
    return request;
};
```

### CloudFormation for Lambda@Edge

```yaml
BasicAuthFunction:
  Type: AWS::Lambda::Function
  Properties:
    Runtime: nodejs18.x
    Handler: index.handler
    Role: !GetAtt LambdaEdgeRole.Arn
    Code:
      ZipFile: |
        # Lambda code here
    Timeout: 5
    MemorySize: 128

BasicAuthFunctionVersion:
  Type: AWS::Lambda::Version
  Properties:
    FunctionName: !Ref BasicAuthFunction

CloudFrontDistribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    DistributionConfig:
      # ... other config
      DefaultCacheBehavior:
        LambdaFunctionAssociations:
          - EventType: viewer-request
            LambdaFunctionARN: !Ref BasicAuthFunctionVersion
```

### Pros and Cons

**Pros:**
- Very simple to implement
- No additional AWS services needed (besides Lambda@Edge)
- Browser handles login UI natively
- Works with any static site
- No JavaScript required

**Cons:**
- Single shared password (no per-user credentials)
- Password sent with every request (even over HTTPS)
- No session management or token refresh
- Cannot track individual users
- No MFA support
- Not suitable for production or compliance
- Limited security
- Password changes require Lambda update

### When to Use Basic Auth

- Development/testing environments
- Internal tools with single team
- Very simple use cases
- Quick demos or prototypes
- **NOT for production customer-facing applications**

---

## Security Considerations

### 1. CORS Configuration

**Strict CORS policy (Production):**
```yaml
Cors:
  AllowOrigin: "'https://your-specific-domain.com'"  # NEVER use '*'
  AllowMethods: "'POST, OPTIONS'"
  AllowHeaders: "'Content-Type,Authorization'"
  AllowCredentials: true
  MaxAge: 600
```

**Development configuration:**
```yaml
# Only for local testing
Cors:
  AllowOrigin: "'http://localhost:8000'"
  AllowMethods: "'POST, OPTIONS'"
  AllowHeaders: "'Content-Type,Authorization'"
```

### 2. Content Security Policy (CSP)

Add to all HTML pages:

```html
<meta http-equiv="Content-Security-Policy"
      content="
        default-src 'self';
        script-src 'self' 'unsafe-inline' https://sdk.amazonaws.com;
        connect-src 'self' https://*.amazonaws.com https://*.amazoncognito.com;
        style-src 'self' 'unsafe-inline';
        img-src 'self' data: https:;
        font-src 'self';
        frame-ancestors 'none';
        base-uri 'self';
        form-action 'self';
      ">
```

Or configure in CloudFront:

```yaml
ResponseHeadersPolicy:
  Type: AWS::CloudFront::ResponseHeadersPolicy
  Properties:
    ResponseHeadersPolicyConfig:
      SecurityHeadersConfig:
        ContentSecurityPolicy:
          ContentSecurityPolicy: "default-src 'self'; ..."
          Override: true
        StrictTransportSecurity:
          AccessControlMaxAgeSec: 63072000
          IncludeSubdomains: true
          Preload: true
          Override: true
        XContentTypeOptions:
          Override: true
```

### 3. Rate Limiting

**API Gateway Throttling:**
```yaml
WebSearchApi:
  Type: AWS::Serverless::Api
  Properties:
    ThrottleSettings:
      BurstLimit: 10      # Max concurrent requests
      RateLimit: 5        # Requests per second per IP
```

**Per-User Quotas:**
```yaml
UsagePlan:
  Type: AWS::ApiGateway::UsagePlan
  Properties:
    ApiStages:
      - ApiId: !Ref WebSearchApi
        Stage: prod
    Quota:
      Limit: 100          # Requests per period
      Period: DAY
    Throttle:
      BurstLimit: 10
      RateLimit: 5
```

**WAF Rate Limiting:**
```yaml
WebACL:
  Type: AWS::WAFv2::WebACL
  Properties:
    Scope: CLOUDFRONT
    DefaultAction:
      Allow: {}
    Rules:
      - Name: RateLimitRule
        Priority: 1
        Statement:
          RateBasedStatement:
            Limit: 100
            AggregateKeyType: IP
        Action:
          Block: {}
```

### 4. Input Validation

**Frontend validation:**
```javascript
function validateQuery(query) {
    // Length check
    if (query.length > 500) {
        throw new Error('Query too long (max 500 characters)');
    }

    // Minimum length
    if (query.trim().length < 3) {
        throw new Error('Query too short (min 3 characters)');
    }

    // Character whitelist
    if (!/^[\w\s\?\.,!'\"-]+$/u.test(query)) {
        throw new Error('Query contains invalid characters');
    }

    // SQL injection patterns (defense in depth)
    const sqlPatterns = /(\bSELECT\b|\bUNION\b|\bDROP\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b)/i;
    if (sqlPatterns.test(query)) {
        throw new Error('Invalid query format');
    }

    return true;
}

function validateParameters(maxResults, maxChunks) {
    if (maxResults < 1 || maxResults > 20) {
        throw new Error('maxResults must be between 1 and 20');
    }
    if (maxChunks < 1 || maxChunks > 50) {
        throw new Error('maxChunks must be between 1 and 50');
    }
}
```

**Backend validation** (already in app.py):
```python
# Lambda already validates:
# - max_results: 1-20
# - max_chunks: 1-50
# - query: required string
```

### 5. Secure Headers

**CloudFront Response Headers:**
```yaml
ResponseHeadersPolicy:
  Type: AWS::CloudFront::ResponseHeadersPolicy
  Properties:
    ResponseHeadersPolicyConfig:
      Name: SecurityHeaders
      SecurityHeadersConfig:
        # Prevent clickjacking
        FrameOptions:
          FrameOption: DENY
          Override: true
        # Prevent MIME sniffing
        XContentTypeOptions:
          Override: true
        # Enable XSS protection
        XSSProtection:
          ModeBlock: true
          Protection: true
          Override: true
        # HTTPS enforcement
        StrictTransportSecurity:
          AccessControlMaxAgeSec: 63072000
          IncludeSubdomains: true
          Preload: true
          Override: true
        # Referrer policy
        ReferrerPolicy:
          ReferrerPolicy: strict-origin-when-cross-origin
          Override: true
```

### 6. Logging and Monitoring

**CloudWatch Log Groups:**
```yaml
ApiGatewayLogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: /aws/apigateway/websearch-llm
    RetentionInDays: 30

CloudFrontLogBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: websearch-llm-cloudfront-logs
    AccessControl: LogDeliveryWrite
    LifecycleConfiguration:
      Rules:
        - ExpirationInDays: 90
          Status: Enabled
```

**CloudWatch Alarms:**
```yaml
HighErrorRateAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: WebSearchLLM-HighErrorRate
    MetricName: 4XXError
    Namespace: AWS/ApiGateway
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 10
    ComparisonOperator: GreaterThanThreshold

UnauthorizedAccessAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: WebSearchLLM-UnauthorizedAccess
    MetricName: Count
    Namespace: AWS/ApiGateway
    Dimensions:
      - Name: ApiName
        Value: !Ref WebSearchApi
    Statistic: Sum
    Period: 60
    EvaluationPeriods: 1
    Threshold: 5
    ComparisonOperator: GreaterThanThreshold
```

### 7. Secrets Management

**DO NOT hardcode credentials in frontend:**
```javascript
// ❌ WRONG - Never hardcode in JavaScript
const config = {
    apiKey: 'abc123...'  // Visible to anyone
};

// ✅ CORRECT - Use Cognito tokens
const token = await authService.getValidToken();
```

**Store sensitive values in Secrets Manager:**
```yaml
# For backend configuration only
CognitoSecrets:
  Type: AWS::SecretsManager::Secret
  Properties:
    Name: websearch-llm/cognito
    SecretString: !Sub |
      {
        "userPoolId": "${CognitoUserPool}",
        "clientId": "${CognitoUserPoolClient}"
      }
```

### 8. DDoS Protection

**AWS Shield Standard** (automatically enabled):
- Protection against common DDoS attacks
- Network/transport layer protection
- No additional cost

**AWS Shield Advanced** (optional, $3000/month):
- Enhanced DDoS protection
- 24/7 DDoS Response Team (DRT)
- Cost protection
- Advanced attack analytics

**CloudFront + WAF:**
```yaml
# Geographic restrictions (optional)
GeoRestriction:
  RestrictionType: whitelist
  Locations:
    - US
    - CA

# IP-based access control
IPSetRule:
  Type: AWS::WAFv2::IPSet
  Properties:
    Addresses:
      - 203.0.113.0/24  # Office IP range
    IPAddressVersion: IPV4
```

---

## Cost Estimation

Monthly costs for **1,000 active users**, **10 queries per user per month** (10,000 total requests):

| Service | Usage | Unit Cost | Monthly Cost |
|---------|-------|-----------|--------------|
| **S3 Storage** | 100 MB | $0.023/GB | $0.002 |
| **S3 Requests** | 10,000 GET | $0.0004/1k | $0.004 |
| **CloudFront** | 1 GB data transfer | $0.085/GB | $0.085 |
| **CloudFront Requests** | 10,000 | $0.0075/10k | $0.008 |
| **Cognito** | 1,000 MAUs | Free tier (50k) | $0.00 |
| **API Gateway** | 10,000 requests | $3.50/million | $0.035 |
| **Lambda Execution** (existing) | 10,000 invocations | ~$8.00 | $8.00 |
| **CloudWatch Logs** | 1 GB ingestion | $0.50/GB | $0.50 |
| **CloudWatch Metrics** | Standard metrics | Free | $0.00 |
| **Data Transfer Out** | 1 GB | $0.09/GB | $0.09 |
| **Route 53** (optional) | 1 hosted zone | $0.50/month | $0.50 |
| **ACM Certificate** (optional) | 1 certificate | Free | $0.00 |
| **Total (Basic)** | | | **~$9.27/month** |
| **Total (with custom domain)** | | | **~$9.77/month** |

### Cost Breakdown by User Scale

| Users | Queries/Month | Monthly Cost |
|-------|---------------|--------------|
| 100 | 1,000 | ~$8.10 |
| 1,000 | 10,000 | ~$9.27 |
| 5,000 | 50,000 | ~$15.50 |
| 10,000 | 100,000 | ~$25.00 |
| 50,000 | 500,000 | ~$105.00 |

### Cost Optimization Tips

1. **Enable CloudFront caching** for static assets (CSS, JS, images)
2. **Use S3 Intelligent-Tiering** for log storage
3. **Set CloudWatch Logs retention** to 7-30 days
4. **Compress responses** with CloudFront compression
5. **Use Lambda reserved concurrency** to prevent unexpected costs
6. **Enable API Gateway caching** for repeated queries (optional)

---

## Deployment Process

### Prerequisites

- AWS CLI configured with appropriate credentials
- SAM CLI installed
- Node.js installed (for frontend build tools)
- Git repository initialized

### Step 1: Update SAM Template

Add Cognito and CloudFront resources to `template.yaml`:

```yaml
# Add to Parameters section
FrontendBucketName:
  Type: String
  Description: S3 bucket name for frontend hosting
  Default: websearch-llm-frontend

# Add to Resources section
CognitoUserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: websearch-llm-users
    # ... (configuration from earlier sections)

CognitoUserPoolClient:
  Type: AWS::Cognito::UserPoolClient
  Properties:
    # ... (configuration from earlier sections)

WebsiteBucket:
  Type: AWS::S3::Bucket
  Properties:
    # ... (configuration from earlier sections)

CloudFrontDistribution:
  Type: AWS::CloudFront::Distribution
  Properties:
    # ... (configuration from earlier sections)

# Update existing API Gateway
WebSearchApi:
  Type: AWS::Serverless::Api
  Properties:
    StageName: prod
    Auth:
      DefaultAuthorizer: CognitoAuthorizer
      Authorizers:
        CognitoAuthorizer:
          UserPoolArn: !GetAtt CognitoUserPool.Arn
    # ... rest of configuration

# Add to Outputs section
CognitoUserPoolId:
  Description: Cognito User Pool ID
  Value: !Ref CognitoUserPool
  Export:
    Name: !Sub '${AWS::StackName}-UserPoolId'

CognitoClientId:
  Description: Cognito Client ID
  Value: !Ref CognitoUserPoolClient
  Export:
    Name: !Sub '${AWS::StackName}-ClientId'

WebsiteURL:
  Description: CloudFront URL for frontend
  Value: !GetAtt CloudFrontDistribution.DomainName
  Export:
    Name: !Sub '${AWS::StackName}-WebsiteURL'

CloudFrontDistributionId:
  Description: CloudFront Distribution ID
  Value: !Ref CloudFrontDistribution
```

### Step 2: Build and Deploy Backend

```bash
# Navigate to project directory
cd /Users/dgwartne/git/websearch-llm

# Build SAM application
sam build

# Deploy with guided deployment
sam deploy --guided

# Follow prompts:
# - Stack Name: websearch-llm
# - AWS Region: us-east-1
# - Confirm changes before deploy: Y
# - Allow SAM CLI IAM role creation: Y
# - Save arguments to configuration file: Y

# After deployment, capture outputs
sam list stack-outputs --stack-name websearch-llm
```

### Step 3: Create Cognito Users

```bash
# Get User Pool ID from outputs
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' \
  --output text)

# Create admin user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username admin@westjet.com \
  --user-attributes \
    Name=email,Value=admin@westjet.com \
    Name=email_verified,Value=true \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS

# User will be forced to change password on first login

# Create additional users
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username user1@westjet.com \
  --user-attributes Name=email,Value=user1@westjet.com \
  --temporary-password "TempPass456!"
```

### Step 4: Configure Frontend

Update `frontend/js/config.js` with deployed values:

```bash
# Get outputs
CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoClientId`].OutputValue' \
  --output text)

API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`WebSearchApiEndpoint`].OutputValue' \
  --output text)

# Update config.js
cat > frontend/js/config.js <<EOF
const config = {
    cognito: {
        userPoolId: '$USER_POOL_ID',
        clientId: '$CLIENT_ID',
        region: 'us-east-1'
    },
    api: {
        endpoint: '$API_ENDPOINT'
    }
};

export { config };
EOF
```

### Step 5: Build Frontend

```bash
cd frontend

# Install dependencies (if using npm)
npm install amazon-cognito-identity-js

# For production, minify JavaScript and CSS
# (optional, using terser and cssnano)
npm install -g terser cssnano-cli

terser js/auth.js -c -m -o js/auth.min.js
terser js/api.js -c -m -o js/api.min.js
terser js/app.js -c -m -o js/app.min.js

cssnano css/styles.css css/styles.min.css
cssnano css/login.css css/login.min.css

# Test locally
python3 -m http.server 8000
# Open http://localhost:8000 in browser
```

### Step 6: Deploy Frontend to S3

```bash
# Get bucket name
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucket`].OutputValue' \
  --output text)

# Sync files to S3
aws s3 sync . s3://$BUCKET_NAME/ \
  --delete \
  --exclude ".git/*" \
  --exclude "node_modules/*" \
  --exclude "*.map"

# Set cache headers for static assets
aws s3 cp s3://$BUCKET_NAME/css/ s3://$BUCKET_NAME/css/ \
  --recursive \
  --metadata-directive REPLACE \
  --cache-control "max-age=31536000, public"

aws s3 cp s3://$BUCKET_NAME/js/ s3://$BUCKET_NAME/js/ \
  --recursive \
  --metadata-directive REPLACE \
  --cache-control "max-age=31536000, public"

aws s3 cp s3://$BUCKET_NAME/assets/ s3://$BUCKET_NAME/assets/ \
  --recursive \
  --metadata-directive REPLACE \
  --cache-control "max-age=31536000, public"

# HTML files should have shorter cache
aws s3 cp s3://$BUCKET_NAME/*.html s3://$BUCKET_NAME/ \
  --recursive \
  --metadata-directive REPLACE \
  --cache-control "max-age=300, public"
```

### Step 7: Invalidate CloudFront Cache

```bash
# Get CloudFront Distribution ID
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

# Create invalidation
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"

# Check invalidation status
aws cloudfront wait invalidation-completed \
  --distribution-id $DISTRIBUTION_ID \
  --id <invalidation-id>
```

### Step 8: Access Application

```bash
# Get CloudFront URL
CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --stack-name websearch-llm \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' \
  --output text)

echo "Access your application at: https://$CLOUDFRONT_URL"
```

### Step 9: (Optional) Configure Custom Domain

```bash
# Request ACM certificate (must be in us-east-1 for CloudFront)
CERT_ARN=$(aws acm request-certificate \
  --domain-name search.westjet.com \
  --validation-method DNS \
  --region us-east-1 \
  --query 'CertificateArn' \
  --output text)

# Validate certificate (follow DNS instructions)
aws acm describe-certificate \
  --certificate-arn $CERT_ARN \
  --region us-east-1

# After validation, update CloudFront distribution
aws cloudfront update-distribution \
  --id $DISTRIBUTION_ID \
  --distribution-config file://distribution-config.json

# Create Route 53 record
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch file://dns-record.json
```

### Deployment Script (Automated)

Create `deploy-frontend.sh`:

```bash
#!/bin/bash
set -e

STACK_NAME="websearch-llm"
REGION="us-east-1"

echo "📦 Deploying frontend for $STACK_NAME..."

# Get stack outputs
echo "🔍 Retrieving stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucket`].OutputValue' \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

echo "  Bucket: $BUCKET_NAME"
echo "  Distribution: $DISTRIBUTION_ID"

# Sync to S3
echo "☁️  Syncing files to S3..."
aws s3 sync frontend/ s3://$BUCKET_NAME/ \
  --delete \
  --exclude ".git/*" \
  --exclude "node_modules/*" \
  --region $REGION

# Invalidate CloudFront
echo "🔄 Invalidating CloudFront cache..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text)

echo "  Invalidation ID: $INVALIDATION_ID"

# Get URL
CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' \
  --output text)

echo "✅ Deployment complete!"
echo "🌐 Access your application at: https://$CLOUDFRONT_URL"
```

Make executable and run:
```bash
chmod +x deploy-frontend.sh
./deploy-frontend.sh
```

---

## Advanced Features

### 1. Query History

Store user queries in DynamoDB for analytics and history:

**DynamoDB Table:**
```yaml
QueryHistoryTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: websearch-llm-query-history
    BillingMode: PAY_PER_REQUEST
    AttributeDefinitions:
      - AttributeName: userId
        AttributeType: S
      - AttributeName: timestamp
        AttributeType: N
    KeySchema:
      - AttributeName: userId
        KeyType: HASH
      - AttributeName: timestamp
        KeyType: RANGE
    TimeToLiveSpecification:
      Enabled: true
      AttributeName: ttl
    StreamSpecification:
      StreamViewType: NEW_AND_OLD_IMAGES
```

**Lambda Integration:**
```python
import boto3
from datetime import datetime, timedelta

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('websearch-llm-query-history')

def save_query_history(user_id, query, response):
    """Save query to DynamoDB"""
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())

    table.put_item(Item={
        'userId': user_id,
        'timestamp': int(datetime.now().timestamp() * 1000),
        'query': query,
        'responseTime': response['metadata']['total_time_ms'],
        'chunksProcessed': response['metadata']['chunks_processed'],
        'urlsScraped': response['metadata']['urls_scraped'],
        'ttl': ttl  # Auto-delete after 90 days
    })
```

**Frontend - Display History:**
```javascript
async function getQueryHistory() {
    const username = authService.getUsername();
    const response = await fetch(`${config.api.endpoint}/history`, {
        headers: {
            'Authorization': `Bearer ${await authService.getValidToken()}`
        }
    });
    return await response.json();
}
```

### 2. Analytics Dashboard

Track and visualize usage metrics:

**CloudWatch Dashboard:**
```yaml
AnalyticsDashboard:
  Type: AWS::CloudWatch::Dashboard
  Properties:
    DashboardName: WebSearchLLM-Analytics
    DashboardBody: !Sub |
      {
        "widgets": [
          {
            "type": "metric",
            "properties": {
              "title": "API Requests",
              "metrics": [
                ["AWS/ApiGateway", "Count", {"stat": "Sum"}]
              ],
              "period": 300,
              "region": "${AWS::Region}"
            }
          },
          {
            "type": "metric",
            "properties": {
              "title": "Lambda Duration",
              "metrics": [
                ["AWS/Lambda", "Duration", {"stat": "Average"}]
              ]
            }
          }
        ]
      }
```

**Custom Metrics:**
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def publish_query_metrics(query_length, response_time):
    cloudwatch.put_metric_data(
        Namespace='WebSearchLLM',
        MetricData=[
            {
                'MetricName': 'QueryLength',
                'Value': query_length,
                'Unit': 'Count'
            },
            {
                'MetricName': 'ResponseTime',
                'Value': response_time,
                'Unit': 'Milliseconds'
            }
        ]
    )
```

### 3. Feedback Mechanism

Collect user feedback on answer quality:

**Frontend:**
```html
<div class="feedback-buttons">
    <button onclick="submitFeedback('positive', queryId)">
        👍 Helpful
    </button>
    <button onclick="submitFeedback('negative', queryId)">
        👎 Not helpful
    </button>
</div>
```

```javascript
async function submitFeedback(sentiment, queryId) {
    await fetch(`${config.api.endpoint}/feedback`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${await authService.getValidToken()}`
        },
        body: JSON.stringify({
            queryId: queryId,
            sentiment: sentiment,
            timestamp: Date.now()
        })
    });

    // Show thank you message
    showNotification('Thank you for your feedback!');
}
```

**Backend - Store Feedback:**
```python
def save_feedback(query_id, user_id, sentiment):
    """Store feedback in DynamoDB"""
    feedback_table.put_item(Item={
        'queryId': query_id,
        'userId': user_id,
        'sentiment': sentiment,
        'timestamp': int(time.time() * 1000)
    })
```

### 4. Voice Input

Integrate Web Speech API for voice queries:

```javascript
class VoiceInput {
    constructor() {
        this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        this.recognition.continuous = false;
        this.recognition.interimResults = false;
        this.recognition.lang = 'en-US';
    }

    async startListening() {
        return new Promise((resolve, reject) => {
            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                resolve(transcript);
            };

            this.recognition.onerror = (event) => {
                reject(event.error);
            };

            this.recognition.start();
        });
    }
}

// Usage
const voiceInput = new VoiceInput();
document.getElementById('voiceBtn').addEventListener('click', async () => {
    try {
        const query = await voiceInput.startListening();
        document.getElementById('queryInput').value = query;
    } catch (error) {
        console.error('Voice input failed:', error);
    }
});
```

**HTML Button:**
```html
<button id="voiceBtn" class="btn-voice" title="Voice input">
    🎤 Voice
</button>
```

### 5. Export Results

Allow users to export search results:

```javascript
function exportResults(data, format = 'json') {
    let content, mimeType, filename;

    switch (format) {
        case 'json':
            content = JSON.stringify(data, null, 2);
            mimeType = 'application/json';
            filename = `search-results-${Date.now()}.json`;
            break;

        case 'txt':
            content = `Query: ${data.query}\n\n` +
                     `Answer:\n${data.answer}\n\n` +
                     `Sources:\n${data.sources.join('\n')}`;
            mimeType = 'text/plain';
            filename = `search-results-${Date.now()}.txt`;
            break;

        case 'csv':
            content = 'Rank,URL,Similarity,Preview\n' +
                     data.source_details.map(s =>
                         `${s.rank},"${s.url}",${s.similarity_score},"${s.content_preview}"`
                     ).join('\n');
            mimeType = 'text/csv';
            filename = `search-sources-${Date.now()}.csv`;
            break;
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// Add export buttons
document.getElementById('exportJson').addEventListener('click', () => {
    exportResults(lastSearchResults, 'json');
});
```

### 6. Dark Mode

Add theme switching:

```javascript
class ThemeManager {
    constructor() {
        this.theme = localStorage.getItem('theme') || 'light';
        this.applyTheme();
    }

    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
    }

    toggle() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', this.theme);
        this.applyTheme();
    }
}

const themeManager = new ThemeManager();
```

**CSS Variables:**
```css
:root[data-theme="light"] {
    --bg-color: #ffffff;
    --text-color: #333333;
}

:root[data-theme="dark"] {
    --bg-color: #1a1a1a;
    --text-color: #e0e0e0;
}

body {
    background: var(--bg-color);
    color: var(--text-color);
}
```

### 7. Progressive Web App (PWA)

Make the site installable as an app:

**manifest.json:**
```json
{
    "name": "WestJet Knowledge Search",
    "short_name": "WestJet Search",
    "description": "Search WestJet knowledge base powered by AI",
    "start_url": "/app.html",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#0066cc",
    "icons": [
        {
            "src": "/assets/icon-192.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/assets/icon-512.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
}
```

**Service Worker (sw.js):**
```javascript
const CACHE_NAME = 'websearch-v1';
const urlsToCache = [
    '/app.html',
    '/css/styles.css',
    '/js/app.js',
    '/js/auth.js',
    '/js/api.js',
    '/assets/logo.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => response || fetch(event.request))
    );
});
```

---

## Summary

### Recommended Solution: Amazon Cognito + CloudFront

**Why this approach:**
- ✅ Enterprise-grade security with JWT tokens
- ✅ Per-user authentication and tracking
- ✅ MFA support for enhanced security
- ✅ Password reset and account recovery
- ✅ Scalable to thousands of users
- ✅ No server management required
- ✅ Audit trail and compliance-ready
- ✅ Cost-effective (~$9/month for 1000 users)

**Implementation Timeline:**
- **Backend (SAM template updates):** 2-3 hours
- **Frontend (HTML/CSS/JavaScript):** 4-6 hours
- **Testing and debugging:** 2-3 hours
- **Documentation:** 1 hour
- **Total: 1-2 days** for a production-ready implementation

**Next Steps:**
1. Update `template.yaml` with Cognito and CloudFront resources
2. Deploy backend with `sam deploy`
3. Create Cognito users
4. Build and configure frontend
5. Deploy frontend to S3
6. Test end-to-end authentication flow
7. Monitor and iterate based on user feedback

This architecture provides a secure, scalable, and maintainable solution for providing a password-protected web interface to your websearch-llm Lambda function.
