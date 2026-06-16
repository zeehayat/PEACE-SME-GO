# Chapter 13: Vue 3 Frontend Foundations

## Purpose

The Vue frontend teaches SPA structure, routing, state stored in localStorage, Axios API calls, bilingual rendering, and component composition.

Application parallel: every Vue concept in this chapter is tied to a PEACE SME screen. You learn `ref` by storing login fields, `reactive` by building the business profile form, `computed` by switching English/Urdu labels, and route guards by protecting applicant/admin pages.

## Foundational Concepts Explained Simply

### 1. SPA vs. MPA Architecture

:::expandable [SPA vs. MPA Architecture]
#### In-Depth Explanation
* **Multi-Page Applications (MPAs):** Traditional sites (e.g., standard Flask or Laravel setups) request a new HTML page from the server on every navigation. The browser window flashes white, stylesheet assets are parsed again, and any local client-side memory state is wiped out.
* **Single Page Applications (SPAs):** Load a single index.html shell containing a JavaScript bundle.
  * **Routing:** Navigation is intercepted client-side via the HTML5 History API (`history.pushState`). The URL path changes, but the browser does not reload. Instead, a routing library (like Vue Router) swaps the active component layout in the DOM.
  * **Data Flow:** The frontend communicates with the Go backend asynchronously by fetching JSON payloads via HTTP requests (`Axios` or `Fetch`).

#### Sandbox Program: Simple Vanilla Client-Side Router
This sandbox demonstrates how client-side routing works in vanilla JavaScript. It intercepts click events, updates the URL history, and dynamically swaps out page views:

```html
<!-- Vanilla HTML SPA Simulator -->
<div id="app">
  <nav>
    <a href="/" onclick="navigate(event, '/')">Home</a> |
    <a href="/about" onclick="navigate(event, '/about')">About</a>
  </nav>
  <div id="view" style="padding: 20px; border: 1px solid #ccc; margin-top: 10px;"></div>
</div>

<script>
// Mock view layouts mapping paths to templates
const routes = {
  '/': '<h1>Home Page</h1><p>Welcome to PEACE SME SPA!</p>',
  '/about': '<h1>About Us</h1><p>We empower regional business rewrite systems.</p>'
};

function renderView(path) {
  const viewElement = document.getElementById('view');
  viewElement.innerHTML = routes[path] || '<h1>404 Not Found</h1>';
}

function navigate(event, path) {
  event.preventDefault(); // Prevent full page browser reload
  window.history.pushState({}, '', path); // Update address bar
  renderView(path); // Update DOM dynamically
}

// Handle browser Back/Forward navigation triggers
window.onpopstate = () => {
  renderView(window.location.pathname);
};

// Initial Render
renderView('/');
</script>
```
:::

### 2. Vue 3 Reactivity System (ES6 Proxies)

:::expandable [Vue 3 Reactivity & ES6 Proxies]
#### In-Depth Explanation
Vue 3's reactivity system tracks variable changes and automatically updates the HTML DOM.
* **Reactivity Mechanism:** Built using native **ES6 Proxies**. When you declare a reactive target via `ref(value)` or `reactive(object)`, Vue wraps the target object in a Proxy instance.
* **Get Trap (Dependency Tracking):** When a component template renders and accesses a reactive property, the Proxy's `get` handler is triggered. Vue registers the calling component as a dependency of that property.
* **Set Trap (DOM Re-rendering):** When the property is modified, the Proxy's `set` handler intercepts the write. It notifies all registered dependency functions to execute, causing the Virtual DOM to compare changes and re-render.

#### Sandbox Program: Custom Reactivity in Vanilla JavaScript
This sandbox implements a lightweight version of Vue's `ref()` function using ES6 Proxies to show how visual DOM updates are triggered whenever a JavaScript property changes:

```html
<!-- Simple Vanilla Reactivity Simulator -->
<div class="card p-4">
  <h2 id="counter-title">Count: 0</h2>
  <button onclick="increment()">Add 1</button>
</div>

<script>
// Mock Vue "ref" implementation using ES6 Proxies
function myRef(initialValue) {
  const container = { value: initialValue };
  
  // Trackers list (effects to run when value changes)
  const subscribers = [];
  
  return new Proxy(container, {
    get(target, key) {
      if (key === 'value' && activeEffect) {
        subscribers.push(activeEffect); // Track dependency
      }
      return target[key];
    },
    set(target, key, newValue) {
      if (key === 'value') {
        target[key] = newValue;
        // Trigger all dependent effects
        subscribers.forEach(effect => effect());
      }
      return true;
    }
  });
}

// Global active effect tracker
let activeEffect = null;

// The reactive state variable
const count = myRef(0);

// Register a renderer effect (acts like Vue's component compile render)
activeEffect = () => {
  document.getElementById('counter-title').innerText = `Count: ${count.value}`;
};
activeEffect(); // Run once initially to register get hook
activeEffect = null; // Clear active tracker

function increment() {
  count.value++; // Mutating value automatically triggers set and updates DOM!
}
</script>
```
:::

### 3. Composition API vs. Options API

:::expandable [Composition API vs. Options API]
#### In-Depth Explanation
* **Options API:** Features are organized by option blocks: `data()`, `methods`, `computed`, `watch`. In complex components with multiple features, code for a single feature is scattered across multiple locations, making it difficult to maintain.
* **Composition API (`<script setup>`):** Organizes code by logical feature concern in a unified script block.
  * **Composables:** Allows you to extract reactive state and business logic into separate, reusable files (e.g. `useAuth.js`) and share them across different components.

#### Sandbox Comparison: Options API vs. Composition API
Compare these two component styles performing the exact same logic. Note how clean, organized, and reusable the Composition API layout is:

##### Options API Style
```js
export default {
  data() {
    return {
      language: 'english'
    }
  },
  computed: {
    isUrdu() {
      return this.language === 'urdu'
    }
  },
  methods: {
    toggleLang() {
      this.language = this.language === 'english' ? 'urdu' : 'english'
    }
  }
}
```

##### Composition API Style (Modular and reusable)
```vue
<script setup>
import { ref, computed } from 'vue'

// Local state
const language = ref('english')

// Computed properties
const isUrdu = computed(() => language.value === 'urdu')

// Actions
function toggleLang() {
  language.value = language.value === 'english' ? 'urdu' : 'english'
}
</script>
```
:::

### External Resources
- [Vue.js Official Guide: Reactivity in Depth](https://vuejs.org/guide/extras/reactivity-in-depth.html)
- [Vue Router Documentation](https://router.vuejs.org/)
- [Axios Getting Started Guide](https://axios-http.com/docs/intro)

---

## Core Vue Concepts

Learn:
- `createApp`
- Single File Components
- Composition API
- `ref`
- `reactive`
- `computed`
- `watch`
- `onMounted`
- props and emits
- Vue Router
- Axios interceptors
- Tailwind utility classes

## Concept to Portal Feature

| Vue concept | PEACE SME use |
|---|---|
| `ref` | login email, password, loading, error |
| `reactive` | business profile form and grant form |
| `computed` | selected translation object and RTL state |
| `watch` | reload admin reports when filters change |
| `onMounted` | fetch dashboard profile and announcements |
| props | reusable input, upload, and table components |
| emits | upload complete, modal close, row selected |
| router guard | redirect unauthenticated users |
| Axios interceptor | attach JWT bearer token |

---

## Application Entry

Recommended structure:

```text
frontend/src/
  main.js
  App.vue
  apiConfig.js
  router/index.js
  api/client.js
  views/
  components/
```

`apiConfig.js` is the single source of truth for the backend base URL.

---

## Route Guards

Preserve:

```text
requiresAuth  -> localStorage.userToken  -> else /login
requiresAdmin -> localStorage.adminToken -> else /admin/login
```

Do not rename token keys unless you update all dependent code.

Application parallel:

- `/dashboard` requires `userToken`.
- `/business-profile` requires `userToken`.
- `/grant-application` requires `userToken`.
- `/admin/dashboard` requires `adminToken`.
- `/admin/grants/submitted/:id` requires `adminToken`.

Frontend guards improve navigation, but the Go backend remains the real security boundary.

---

## Axios Client

Create one Axios instance. Attach tokens based on route area or helper calls:

```js
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('userToken')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

For admin calls, either use a second admin client or explicit helper that attaches `adminToken`.

---

## Bilingual UI

Language storage:

```js
localStorage.setItem('language', 'urdu')
```

Computed state:

```js
const isUrdu = computed(() => localStorage.getItem('language') === 'urdu')
```

Rendering:

```vue
<h1 :class="{ 'text-right font-urdu': isUrdu }">{{ t.title }}</h1>
```

Store values in English even when labels render in Urdu.

---

## Tailwind Discipline

Use Tailwind for layout, spacing, typography, and responsive states. Keep repeated visual patterns in components:
- `Navbar.vue`
- `AdminNavbar.vue`
- `Footer.vue`
- drawers
- modals
- upload controls
- table controls

---

## Practical Examples

### Example 1: Vue 3 Single File Component (SFC)
This complete example demonstrates the Composition API (`<script setup>`) syntax, reactivity (`ref`, `computed`), lifecycle hooks (`onMounted`), and dynamic RTL layouts for Urdu translation:

```vue
<!-- File: src/views/WelcomeBanner.vue -->
<script setup>
import { ref, computed, onMounted } from 'vue'

// Reactive state
const name = ref('')
const language = ref(localStorage.getItem('language') || 'english')

// Translation object
const translations = {
  english: {
    welcome: 'Welcome to PEACE SME Grant Portal',
    placeholder: 'Enter your name',
  },
  urdu: {
    welcome: 'پی اے سی ای ایس ایم ای گرانٹ پورٹل میں خوش آمدید',
    placeholder: 'اپنا نام درج کریں',
  }
}

// Computed property for language detection
const isUrdu = computed(() => language.value === 'urdu')

// Computed translations
const t = computed(() => translations[language.value])

// Lifecycle Hook
onMounted(() => {
  console.log('Welcome component mounted successfully.')
})
</script>

<template>
  <div :class="[isUrdu ? 'text-right rtl font-urdu' : 'text-left ltr', 'p-6 bg-white shadow rounded-lg']">
    <h1 class="text-2xl font-bold text-slate-800 mb-4">
      {{ t.welcome }} <span v-if="name" class="text-blue-600">{{ name }}</span>
    </h1>
    
    <label class="block text-sm font-medium text-gray-700 mb-2">{{ t.placeholder }}</label>
    <input 
      v-model="name" 
      type="text" 
      class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500" 
      :placeholder="t.placeholder"
    />
  </div>
</template>

<style scoped>
.font-urdu {
  font-family: 'Noto Nastaliq Urdu', sans-serif;
  line-height: 2.2;
}
</style>
```

### Example 2: Configuring Axios Interceptors globally
This example shows how to set up an Axios instance that intercepts all requests to inject bearer tokens from `localStorage` dynamically:

```js
// File: src/api/client.js
import axios from 'axios'
import apiConfig from '../apiConfig'

const apiClient = axios.create({
  baseURL: apiConfig.baseURL,
  timeout: 10000, // 10 seconds
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request Interceptor: Attach authentication tokens dynamically
apiClient.interceptors.request.use(
  (config) => {
    // Check if route is admin, use admin token; else use user token
    const isAdminRoute = window.location.pathname.startsWith('/admin')
    const tokenKey = isAdminRoute ? 'adminToken' : 'userToken'
    const token = localStorage.getItem(tokenKey)

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response Interceptor: Handle errors (like 401 Unauthorized) globally
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      log.error('Unauthorized access detected. Redirecting to login.')
      // Invalidate tokens and redirect
      localStorage.removeItem('userToken')
      localStorage.removeItem('adminToken')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

---

## Complete Axios Client Setup

The portal needs three separate Axios instances because each actor type uses a different token and different token key in localStorage.

```js
// File: src/api/client.js
import axios from 'axios'
import router from '../router'

const BASE = 'http://localhost:5000/api'

// ── User client ─────────────────────────────────────────────────────────────
export const userApi = axios.create({ baseURL: BASE })

userApi.interceptors.request.use(config => {
    const token = localStorage.getItem('userToken')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

userApi.interceptors.response.use(null, err => {
    if (err.response?.status === 401) {
        localStorage.removeItem('userToken')
        router.push('/login')
    }
    return Promise.reject(err)
})

// ── Admin client ─────────────────────────────────────────────────────────────
export const adminApi = axios.create({ baseURL: BASE })

adminApi.interceptors.request.use(config => {
    const token = localStorage.getItem('adminToken')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

adminApi.interceptors.response.use(null, err => {
    if (err.response?.status === 401) {
        localStorage.removeItem('adminToken')
        router.push('/admin/login')
    }
    return Promise.reject(err)
})

// ── Committee client ──────────────────────────────────────────────────────────
export const committeeApi = axios.create({ baseURL: BASE })

committeeApi.interceptors.request.use(config => {
    const token = localStorage.getItem('committeeToken')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})
```

The response interceptors handle expired tokens globally. Every component that calls `userApi` automatically redirects to `/login` on 401 — no per-component handling required.

---

## Complete Vue Router with Guards

```js
// File: src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

// Public views
import LandingPage from '../views/LandingPage.vue'
import UserLogin from '../views/UserLogin.vue'
import AdminLogin from '../views/AdminLogin.vue'
import CommitteeLogin from '../views/CommitteeLogin.vue'

// Applicant views (requires userToken)
import AppDashboard from '../views/AppDashboard.vue'
import SmeBusinessProfile from '../views/SmeBusinessProfile.vue'
import SmeGrantApplication from '../views/SmeGrantApplication.vue'

// Admin views (requires adminToken)
import AdminDashboard from '../views/admin/AdminDashboard.vue'
import AdminApplicants from '../views/admin/AdminApplicants.vue'

// Committee views (requires committeeToken)
import CommitteeDashboard from '../views/committee/CommitteeDashboard.vue'

const routes = [
    // ── Public ───────────────────────────────────────────────────────────
    { path: '/', component: LandingPage },
    { path: '/login', component: UserLogin },
    { path: '/admin/login', component: AdminLogin },
    { path: '/committee/login', component: CommitteeLogin },

    // ── Applicant (requires userToken) ────────────────────────────────────
    {
        path: '/dashboard',
        component: AppDashboard,
        meta: { requiresAuth: true },
    },
    {
        path: '/business-profile',
        component: SmeBusinessProfile,
        meta: { requiresAuth: true },
    },
    {
        path: '/grant-application',
        component: SmeGrantApplication,
        meta: { requiresAuth: true },
    },

    // ── Admin (requires adminToken) ───────────────────────────────────────
    {
        path: '/admin/dashboard',
        component: AdminDashboard,
        meta: { requiresAdmin: true },
    },
    {
        path: '/admin/applicants',
        component: AdminApplicants,
        meta: { requiresAdmin: true },
    },

    // ── Committee (requires committeeToken) ───────────────────────────────
    {
        path: '/committee/dashboard',
        component: CommitteeDashboard,
        meta: { requiresCommittee: true },
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// Navigation guard — runs before every route change
router.beforeEach((to, from, next) => {
    if (to.meta.requiresAuth && !localStorage.getItem('userToken')) {
        return next('/login')
    }
    if (to.meta.requiresAdmin && !localStorage.getItem('adminToken')) {
        return next('/admin/login')
    }
    if (to.meta.requiresCommittee && !localStorage.getItem('committeeToken')) {
        return next('/committee/login')
    }
    next()
})

export default router
```

The guard runs for every navigation. The Go backend also verifies every JWT, so if the token is valid in localStorage but expired, the Axios response interceptor handles the resulting 401.

---

## Composables: Reusable Stateful Logic

Vue 3 composables are functions that return reactive state and methods. They let you extract logic that appears in multiple components without duplicating code.

### `useAuth.js`

```js
// File: src/composables/useAuth.js
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { userApi, adminApi } from '../api/client'

export function useAuth() {
    const router = useRouter()

    // Reactive reads from localStorage
    const isLoggedIn = computed(() => !!localStorage.getItem('userToken'))
    const isAdmin = computed(() => !!localStorage.getItem('adminToken'))
    const language = computed(() => localStorage.getItem('language') || 'en')

    async function loginUser(email, password) {
        const { data } = await userApi.post('/login', {
            email_address: email,
            password: password,
        })
        localStorage.setItem('userToken', data.token)
        localStorage.setItem('language', data.language)
        router.push('/dashboard')
    }

    async function loginAdmin(username, password) {
        const { data } = await adminApi.post('/admin/login', {
            username,
            password,
        })
        localStorage.setItem('adminToken', data.token)
        router.push('/admin/dashboard')
    }

    function logoutUser() {
        localStorage.removeItem('userToken')
        router.push('/login')
    }

    function logoutAdmin() {
        localStorage.removeItem('adminToken')
        router.push('/admin/login')
    }

    return { isLoggedIn, isAdmin, language, loginUser, loginAdmin, logoutUser, logoutAdmin }
}
```

### `usePagination.js`

```js
// File: src/composables/usePagination.js
import { ref, reactive } from 'vue'

export function usePagination(fetchFn, defaultPerPage = 20) {
    const page = ref(1)
    const perPage = ref(defaultPerPage)
    const total = ref(0)
    const items = ref([])
    const loading = ref(false)
    const error = ref('')

    async function load(extraParams = {}) {
        loading.value = true
        error.value = ''
        try {
            const { data } = await fetchFn({
                page: page.value,
                per_page: perPage.value,
                ...extraParams,
            })
            items.value = data.data
            total.value = data.total
        } catch (err) {
            error.value = err.response?.data?.message || 'Failed to load data.'
        } finally {
            loading.value = false
        }
    }

    function goTo(n) {
        page.value = n
        load()
    }

    const totalPages = ref(0)
    // Compute total pages whenever total or perPage changes
    // (caller uses watchEffect or computed on these)

    return { page, perPage, total, items, loading, error, load, goTo }
}
```

Usage in a component:
```vue
<script setup>
import { onMounted, watch } from 'vue'
import { usePagination } from '../composables/usePagination'
import { adminApi } from '../api/client'

const { page, items, total, loading, load, goTo } = usePagination(
    (params) => adminApi.get('/admin/applicants/report', { params })
)

onMounted(() => load())
</script>
```

### `useLanguage.js`

```js
// File: src/composables/useLanguage.js
import { ref, computed } from 'vue'

const labels = {
    en: {
        businessName:    'Business Name',
        district:        'District',
        grantAmount:     'Grant Amount Required',
        submit:          'Submit Application',
        loading:         'Loading...',
        loginTitle:      'Sign In',
        emailLabel:      'Email Address',
        passwordLabel:   'Password',
        dashboard:       'Dashboard',
    },
    ur: {
        businessName:    'کاروبار کا نام',
        district:        'ضلع',
        grantAmount:     'گرانٹ کی مطلوبہ رقم',
        submit:          'درخواست جمع کریں',
        loading:         'لوڈ ہو رہا ہے...',
        loginTitle:      'سائن ان کریں',
        emailLabel:      'ای میل پتہ',
        passwordLabel:   'پاس ورڈ',
        dashboard:       'ڈیش بورڈ',
    }
}

export function useLanguage() {
    const lang = ref(localStorage.getItem('language') || 'en')

    const t = computed(() => labels[lang.value] || labels.en)
    const isRTL = computed(() => lang.value === 'ur')

    function setLanguage(code) {
        lang.value = code
        localStorage.setItem('language', code)
        // Apply RTL to the document root
        document.documentElement.setAttribute('dir', code === 'ur' ? 'rtl' : 'ltr')
    }

    return { lang, t, isRTL, setLanguage }
}
```

Usage in any component:
```vue
<script setup>
import { useLanguage } from '../composables/useLanguage'
const { t, isRTL } = useLanguage()
</script>

<template>
  <div :dir="isRTL ? 'rtl' : 'ltr'">
    <label>{{ t.businessName }}</label>
  </div>
</template>
```

---

## Mastery Check

You understand this chapter when you can:
- Build a route-protected Vue page using `meta: { requiresAuth: true }` and a `beforeEach` guard.
- Create separate Axios instances for user, admin, and committee tokens.
- Explain what an Axios response interceptor does and why it handles 401 globally.
- Write a composable (`useAuth`, `usePagination`, `useLanguage`) and explain why composables are better than duplicating logic in each component.
- Store and read JWTs from localStorage using the exact key names the Go backend expects.
- Switch English/Urdu labels using a `computed()` property wrapping a translation dictionary.
