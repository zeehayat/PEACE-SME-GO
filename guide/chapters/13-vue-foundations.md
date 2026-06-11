# Chapter 13: Vue 3 Frontend Foundations

## Purpose

The Vue frontend teaches SPA structure, routing, state stored in localStorage, Axios API calls, bilingual rendering, and component composition.

Application parallel: every Vue concept in this chapter is tied to a PEACE SME screen. You learn `ref` by storing login fields, `reactive` by building the business profile form, `computed` by switching English/Urdu labels, and route guards by protecting applicant/admin pages.

## Theoretical Background

### SPA vs. MPA Architecture
Traditional web applications (Multi-Page Applications or **MPAs**) fetch a completely new HTML document from the server on every navigation link clicked:
- **Single Page Applications (SPAs)** load a single HTML shell page once.
- Navigation is handled client-side using JavaScript (via the **HTML5 History API** or hash changes).
- The router dynamically updates the DOM and swaps views without performing full page refreshes, resulting in smooth transitions.
- Data fetching occurs in the background via asynchronous HTTP requests (`fetch` or `Axios`), swapping JSON payloads.

### Vue 3 Reactivity System (ES6 Proxies)
Vue 3 uses JavaScript **ES6 Proxies** to drive its reactivity engine:
- When a reactive object is initialized (`reactive()` or `ref()`), Vue wraps it in a Proxy.
- **Dependency Tracking (Get):** When a component renders and accesses a reactive property, Vue records it as a dependency (called "tracking").
- **Visual Re-rendering (Set):** When a reactive property changes, the proxy traps the write, notifying the dependent components to re-run their render functions and update the DOM (called "triggering").

```text
[ Data Change (Set) ] -> [ Proxy Trap ] -> [ Trigger Effect ] -> [ Virtual DOM Diff ] -> [ DOM Render ]
```

### Composition API vs. Options API
- **Options API:** Groups component code by option types: `data()`, `methods`, `computed`, `watch`. This can lead to fragmented feature logic in large components.
- **Composition API (Vue 3):** Uses a single `setup()` function or `<script setup>` syntax. It allows you to group code by logical features and extract stateful logic into reusable functions called **Composables** (e.g., `useAuth()`).

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

## Mastery Check

You understand this chapter when you can:
- Build a route-protected Vue page.
- Fetch backend JSON with Axios.
- Store and read JWTs from localStorage.
- Switch English/Urdu labels without changing stored values.
- Use Composition API instead of Options API for new code.
