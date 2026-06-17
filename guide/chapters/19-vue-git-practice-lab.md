# Chapter 19: Vue and Git Practice Lab

## Purpose

This lab makes Vue and Git practical. You will build frontend behavior that matches the Go API while using Git to protect every step. Every lab section connects to a real PEACE SME portal screen.

---

## Vue 3 Core Concepts Map

| Vue concept | Portal feature | What you learn |
|---|---|---|
| `ref` | login email/password fields | single primitive reactive values |
| `reactive` | business profile form | object-shaped form state |
| `computed` | Urdu/English label selection | derived state |
| `watch` | filters triggering report reloads | reacting to changes |
| `watchEffect` | auto-fetch when params change | effect-based reactivity |
| `onMounted` | fetch dashboard data | lifecycle fetching |
| props | reusable form input | parent-to-child data |
| emits | modal close, upload complete | child-to-parent events |
| provide/inject | theme, language, auth state | cross-component context |
| composables | `useAuth`, `useLanguage`, `usePagination` | reusable stateful logic |
| Axios interceptors | bearer auth headers, 401 redirect | API integration |
| `<Suspense>` | async component loading | loading states |
| router guards | protected dashboard/admin pages | client-side auth flow |
| Vitest | component unit tests | test the UI logic |

---

## Part 1: Reactivity Deep Dive

### ref vs reactive

`ref` wraps a single value. You access or mutate it through `.value`:

```javascript
import { ref } from 'vue'

const email = ref('')
const loading = ref(false)
const count = ref(0)

// Read
console.log(email.value)

// Write
email.value = 'new@example.com'
count.value++
```

`reactive` wraps an object. Properties are accessed directly, no `.value`:

```javascript
import { reactive } from 'vue'

const form = reactive({
  name_of_business: '',
  business_location_district: '',
  male_employees: 0,
  female_employees: 0,
})

// Read / write directly
form.name_of_business = 'Khyber Tech'
console.log(form.male_employees)
```

> [!NOTE]
> Use `ref` for primitives (strings, numbers, booleans). Use `reactive` for objects, especially forms. Never destructure a `reactive` object — you lose reactivity: `const { name } = reactive({name: ''})` is now a plain string.

### computed — Derived State for Bilingual Labels

The bilingual label system uses `computed` to derive the active translation object:

```javascript
import { computed } from 'vue'
import { useLanguage } from '../composables/useLanguage'

const translations = {
  en: {
    loginHeading: 'Login to Your Account',
    emailLabel: 'Email Address',
    passwordLabel: 'Password',
    loginButton: 'Login',
    forgotPassword: 'Forgot Password?',
  },
  ur: {
    loginHeading: 'اپنے اکاؤنٹ میں لاگ ان کریں',
    emailLabel: 'ای میل ایڈریس',
    passwordLabel: 'پاسورڈ',
    loginButton: 'لاگ ان',
    forgotPassword: 'پاسورڈ بھول گئے؟',
  },
}

const { isUrdu } = useLanguage()
const t = computed(() => isUrdu.value ? translations.ur : translations.en)

// In template:
// {{ t.loginHeading }}
// <input :placeholder="t.emailLabel" />
```

### watchEffect vs watch

`watch` explicitly tracks a source and runs when it changes:

```javascript
import { watch, ref } from 'vue'

const searchQuery = ref('')
const results = ref([])

// Runs when searchQuery changes
watch(searchQuery, async (newQuery) => {
  if (newQuery.length > 2) {
    const { data } = await api.get(`/faqs/search?q=${newQuery}`)
    results.value = data
  } else {
    results.value = []
  }
})
```

`watchEffect` runs immediately and tracks every reactive dependency it accesses:

```javascript
import { watchEffect, ref } from 'vue'

const page = ref(1)
const perPage = ref(20)
const district = ref('')
const applicants = ref([])

// Runs immediately, then re-runs whenever page, perPage, or district change
watchEffect(async () => {
  const { data } = await api.get('/admin/applicants/report', {
    params: {
      page: page.value,
      per_page: perPage.value,
      district: district.value,
    },
  })
  applicants.value = data.data
})
```

---

## Part 2: Composables — Reusable Logic

A composable is a function that uses Vue's composition API internally and returns reactive state or functions.

### useLanguage

```javascript
// File: src/composables/useLanguage.js
import { computed, ref } from 'vue'

// Shared singleton — all components using useLanguage see the same state
const language = ref(localStorage.getItem('language') || 'english')

export function useLanguage() {
  const isUrdu = computed(() => language.value === 'urdu')

  function setLanguage(lang) {
    language.value = lang
    localStorage.setItem('language', lang)
    // Update document direction for RTL support
    document.documentElement.dir = lang === 'urdu' ? 'rtl' : 'ltr'
    document.documentElement.lang = lang === 'urdu' ? 'ur' : 'en'
  }

  function toggleLanguage() {
    setLanguage(isUrdu.value ? 'english' : 'urdu')
  }

  return { language, isUrdu, setLanguage, toggleLanguage }
}
```

Usage in any component:

```vue
<script setup>
import { useLanguage } from '../composables/useLanguage'
const { isUrdu, toggleLanguage } = useLanguage()
</script>

<template>
  <button @click="toggleLanguage">
    {{ isUrdu ? 'English' : 'اردو' }}
  </button>
</template>
```

### useAuth

```javascript
// File: src/composables/useAuth.js
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'

const userToken = ref(localStorage.getItem('userToken'))
const adminToken = ref(localStorage.getItem('adminToken'))

export function useAuth() {
  const router = useRouter()
  const isAuthenticated = computed(() => !!userToken.value)
  const isAdminAuthenticated = computed(() => !!adminToken.value)

  async function login(email, password) {
    const { data } = await api.post('/login', {
      email_address: email,
      password: password,
    })
    userToken.value = data.token
    localStorage.setItem('userToken', data.token)
    return data
  }

  function logout() {
    userToken.value = null
    localStorage.removeItem('userToken')
    router.push('/login')
  }

  async function adminLogin(username, password) {
    const { data } = await api.post('/admin/login', { username, password })
    adminToken.value = data.token
    localStorage.setItem('adminToken', data.token)
    return data
  }

  function adminLogout() {
    adminToken.value = null
    localStorage.removeItem('adminToken')
    router.push('/admin/login')
  }

  return {
    isAuthenticated,
    isAdminAuthenticated,
    userToken,
    adminToken,
    login,
    logout,
    adminLogin,
    adminLogout,
  }
}
```

### usePagination

```javascript
// File: src/composables/usePagination.js
import { computed, ref } from 'vue'

export function usePagination(defaultPerPage = 20) {
  const page = ref(1)
  const perPage = ref(defaultPerPage)
  const total = ref(0)

  const totalPages = computed(() => Math.ceil(total.value / perPage.value))
  const hasNext = computed(() => page.value < totalPages.value)
  const hasPrev = computed(() => page.value > 1)

  function setPage(n) {
    if (n >= 1 && n <= totalPages.value) {
      page.value = n
    }
  }

  function setTotal(n) {
    total.value = n
  }

  function reset() {
    page.value = 1
    total.value = 0
  }

  return {
    page, perPage, total, totalPages, hasNext, hasPrev,
    setPage, setTotal, reset,
  }
}
```

---

## Part 3: Vue Router Guards with JWT

The route guard reads tokens from `localStorage` before every navigation:

```javascript
// File: src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('../views/MainLandingPage.vue') },
  { path: '/login', component: () => import('../views/UserLogin.vue') },
  {
    path: '/dashboard',
    component: () => import('../views/AppDashboard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/business-profile',
    component: () => import('../views/SmeBusinessProfile.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/grant-application',
    component: () => import('../views/SmeGrantApplication.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/login',
    component: () => import('../views/AdminLogin.vue'),
  },
  {
    path: '/admin/dashboard',
    component: () => import('../views/AdminDashboard.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/applicants/report',
    component: () => import('../views/AdminApplicantsReport.vue'),
    meta: { requiresAdmin: true },
  },
  // ... all other routes
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const userToken = localStorage.getItem('userToken')
  const adminToken = localStorage.getItem('adminToken')

  if (to.meta.requiresAuth && !userToken) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  if (to.meta.requiresAdmin && !adminToken) {
    next('/admin/login')
    return
  }

  next()
})

export default router
```

### Redirect After Login

Preserve the intended destination across the login redirect:

```javascript
// In UserLogin.vue
const route = useRoute()
const router = useRouter()

async function login() {
  const data = await authStore.login(email.value, password.value)
  // Redirect to original destination or dashboard
  const redirect = route.query.redirect || '/dashboard'
  router.push(redirect)
}
```

---

## Part 4: Axios Interceptors

Axios interceptors fire on every request or response. Use them for:
- Injecting the auth token (request interceptor)
- Handling 401 responses globally (response interceptor)

```javascript
// File: src/api/client.js
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Request interceptor — inject auth token ──────────────────────────────────
api.interceptors.request.use((config) => {
  // Decide which token to use based on the URL path
  const isAdminRoute = config.url?.startsWith('/admin/')
  const token = isAdminRoute
    ? localStorage.getItem('adminToken')
    : localStorage.getItem('userToken')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

// ── Response interceptor — handle auth errors ─────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid — clear storage and redirect
      localStorage.removeItem('userToken')
      localStorage.removeItem('adminToken')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
```

### Admin API Client

For admin routes, you might want a separate client that only reads `adminToken`:

```javascript
// File: src/api/adminClient.js
import axios from 'axios'

const adminApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 60_000,
})

adminApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('adminToken')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

adminApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('adminToken')
      window.location.href = '/admin/login'
    }
    return Promise.reject(error)
  }
)

export default adminApi
```

---

## Part 5: Lab 1 — Login Page (Complete)

```vue
<!-- File: src/views/UserLogin.vue -->
<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api/client'
import { useLanguage } from '../composables/useLanguage'

const router = useRouter()
const route = useRoute()
const { isUrdu } = useLanguage()

// Form state
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

// Bilingual labels
const translations = {
  en: {
    heading: 'Login to Your Account',
    emailLabel: 'Email Address',
    passwordLabel: 'Password',
    loginButton: 'Login',
    blockedError: 'Your account has been blocked. Contact support.',
    genericError: 'Invalid email or password.',
  },
  ur: {
    heading: 'اپنے اکاؤنٹ میں لاگ ان کریں',
    emailLabel: 'ای میل ایڈریس',
    passwordLabel: 'پاسورڈ',
    loginButton: 'لاگ ان',
    blockedError: 'آپ کا اکاؤنٹ بلاک کر دیا گیا ہے۔ سپورٹ سے رابطہ کریں۔',
    genericError: 'غلط ای میل یا پاسورڈ۔',
  },
}
const t = computed(() => isUrdu.value ? translations.ur : translations.en)

async function login() {
  error.value = ''
  loading.value = true

  try {
    const { data } = await api.post('/login', {
      email_address: email.value,
      password: password.value,
    })

    localStorage.setItem('userToken', data.token)
    localStorage.setItem('language', data.language || 'english')

    const redirect = route.query.redirect || '/dashboard'
    router.push(redirect)

  } catch (err) {
    if (err.response?.status === 403) {
      error.value = t.value.blockedError
    } else {
      error.value = t.value.genericError
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div :class="{ 'text-right font-urdu': isUrdu }" class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="bg-white rounded-xl shadow p-8 w-full max-w-md">
      <h1 data-cy="login-heading" class="text-2xl font-bold text-gray-800 mb-6">
        {{ t.heading }}
      </h1>

      <form @submit.prevent="login" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            {{ t.emailLabel }}
          </label>
          <input
            data-cy="email-input"
            v-model="email"
            type="email"
            required
            class="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            {{ t.passwordLabel }}
          </label>
          <input
            data-cy="password-input"
            v-model="password"
            type="password"
            required
            class="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <p
          v-if="error"
          data-cy="error-message"
          class="text-red-600 text-sm"
        >
          {{ error }}
        </p>

        <button
          data-cy="login-button"
          type="submit"
          :disabled="loading"
          class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium
                 hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '...' : t.loginButton }}
        </button>
      </form>
    </div>
  </div>
</template>
```

---

## Part 6: Lab 2 — Business Profile Form

```vue
<!-- File: src/views/SmeBusinessProfile.vue (abbreviated) -->
<script setup>
import { reactive, ref, onMounted } from 'vue'
import { computed } from 'vue'
import api from '../api/client'
import { useLanguage } from '../composables/useLanguage'

const { isUrdu } = useLanguage()
const saving = ref(false)
const loadingProfile = ref(true)
const successMessage = ref('')
const errorMessage = ref('')
const isEdit = ref(false)

const allowedDistricts = [
  'Swat', 'Shangla', 'Upper Dir', 'Upper Chitral', 'Lower Chitral'
]

const form = reactive({
  name_of_business: '',
  business_registration_number: '',
  business_full_address: '',
  business_location_district: '',
  business_sector: '',
  male_employees: 0,
  female_employees: 0,
  social_media_page: '',
  how_did_you_hear: '',
})

// Load existing profile if it exists
onMounted(async () => {
  try {
    const { data } = await api.get('/business')
    if (data && data.business_id) {
      // Populate form with existing data
      Object.assign(form, data)
      isEdit.value = true
    }
  } catch (err) {
    // No profile yet — that's fine, create mode
  } finally {
    loadingProfile.value = false
  }
})

async function saveProfile() {
  saving.value = true
  successMessage.value = ''
  errorMessage.value = ''

  try {
    if (isEdit.value) {
      await api.put('/business', form)
    } else {
      await api.post('/business', form)
      isEdit.value = true
    }
    successMessage.value = isUrdu.value
      ? 'پروفائل محفوظ ہو گئی'
      : 'Profile saved successfully'
  } catch (err) {
    const msg = err.response?.data?.error || 'Failed to save profile'
    errorMessage.value = msg
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="loadingProfile" class="text-center py-8">Loading...</div>
  <form v-else @submit.prevent="saveProfile" :class="{ 'text-right font-urdu': isUrdu }">
    <div class="mb-4">
      <label class="block font-medium mb-1">
        {{ isUrdu ? 'کاروبار کا نام' : 'Business Name' }}
      </label>
      <input v-model="form.name_of_business" required
             class="w-full border rounded p-2" />
    </div>

    <div class="mb-4">
      <label class="block font-medium mb-1">
        {{ isUrdu ? 'ضلع' : 'District' }}
      </label>
      <select v-model="form.business_location_district" required
              class="w-full border rounded p-2">
        <option value="">-- Select District --</option>
        <option v-for="d in allowedDistricts" :key="d" :value="d">{{ d }}</option>
      </select>
    </div>

    <p v-if="successMessage" class="text-green-600 mb-4">{{ successMessage }}</p>
    <p v-if="errorMessage" class="text-red-600 mb-4">{{ errorMessage }}</p>

    <button type="submit" :disabled="saving"
            class="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700">
      {{ saving ? 'Saving...' : (isUrdu ? 'محفوظ کریں' : 'Save Profile') }}
    </button>
  </form>
</template>
```

---

## Part 7: Lab 3 — Grant Application Dynamic Sections

The grant form has conditional sections based on user input:

```vue
<script setup>
import { reactive, computed } from 'vue'
import { useLanguage } from '../composables/useLanguage'

const { isUrdu } = useLanguage()

const form = reactive({
  // Section 4: Financed items (repeating rows)
  financed_items: [{ item: '', quantity: 1, estimated_cost: null }],

  // Section 5: Contribution
  contribution_type: '',     // 'Cash/Financial' | 'In-kind...' | 'Both'
  financial_amount: null,
  financial_amount_words: '',
  inkind_details: '',
  inkind_value: null,

  // Section 7: Disclaimer
  has_srsp_relative: false,
  srsp_relatives: [],  // [{name, position, office}]

  declaration_accepted: false,
  declaration_name: '',
})

// Derived booleans for conditional visibility
const showCashFields = computed(() =>
  form.contribution_type === 'Cash/Financial' ||
  form.contribution_type === 'Both'
)
const showInkindFields = computed(() =>
  form.contribution_type === 'In-kind (materials, equipment, services)' ||
  form.contribution_type === 'Both'
)

function addItem() {
  form.financed_items.push({ item: '', quantity: 1, estimated_cost: null })
}
function removeItem(i) {
  form.financed_items.splice(i, 1)
}

function addRelative() {
  form.srsp_relatives.push({ name: '', position: '', office: '' })
}
function removeRelative(i) {
  form.srsp_relatives.splice(i, 1)
}
</script>

<template>
  <!-- Section 4: Financed Items -->
  <section class="mb-8">
    <h3 class="font-semibold mb-4">
      {{ isUrdu ? 'مالی اعانت کی اشیاء' : 'Items to be Financed' }}
    </h3>

    <div v-for="(item, i) in form.financed_items" :key="i"
         class="flex gap-3 mb-3 items-start">
      <div class="flex-1">
        <label class="text-xs text-gray-500">{{ isUrdu ? 'آئٹم' : 'Item' }}</label>
        <input v-model="item.item" class="w-full border rounded p-2 text-sm" />
      </div>
      <div class="w-20">
        <label class="text-xs text-gray-500">{{ isUrdu ? 'مقدار' : 'Qty' }}</label>
        <input v-model.number="item.quantity" type="number" min="1"
               class="w-full border rounded p-2 text-sm" />
      </div>
      <div class="w-36">
        <label class="text-xs text-gray-500">{{ isUrdu ? 'لاگت' : 'Est. Cost (PKR)' }}</label>
        <input v-model.number="item.estimated_cost" type="number" min="0"
               class="w-full border rounded p-2 text-sm" />
      </div>
      <button @click="removeItem(i)" v-if="form.financed_items.length > 1"
              class="mt-5 text-red-500 hover:text-red-700">✕</button>
    </div>

    <button type="button" @click="addItem"
            class="text-blue-600 text-sm hover:underline">
      + {{ isUrdu ? 'آئٹم شامل کریں' : 'Add Item' }}
    </button>
  </section>

  <!-- Section 5: Contribution — conditional cash/in-kind fields -->
  <section class="mb-8">
    <h3 class="font-semibold mb-4">
      {{ isUrdu ? 'آپ کا حصہ' : 'Your Contribution' }}
    </h3>

    <select v-model="form.contribution_type" class="border rounded p-2 mb-4">
      <option value="">-- Select --</option>
      <option value="Cash/Financial">Cash/Financial</option>
      <option value="In-kind (materials, equipment, services)">In-kind</option>
      <option value="Both">Both</option>
    </select>

    <!-- Cash fields: only shown when contribution type includes cash -->
    <div v-if="showCashFields" class="mb-4 p-4 bg-blue-50 rounded">
      <label class="block font-medium mb-1">Cash Amount (PKR)</label>
      <input v-model.number="form.financial_amount" type="number" min="0"
             class="border rounded p-2 w-full mb-2" />
      <label class="block font-medium mb-1">Amount in Words</label>
      <input v-model="form.financial_amount_words"
             class="border rounded p-2 w-full" />
    </div>

    <!-- In-kind fields: only shown when contribution type includes in-kind -->
    <div v-if="showInkindFields" class="mb-4 p-4 bg-green-50 rounded">
      <label class="block font-medium mb-1">In-kind Details</label>
      <textarea v-model="form.inkind_details" rows="3"
                class="border rounded p-2 w-full mb-2"></textarea>
      <label class="block font-medium mb-1">In-kind Value (PKR)</label>
      <input v-model.number="form.inkind_value" type="number" min="0"
             class="border rounded p-2 w-full" />
    </div>
  </section>

  <!-- Section 7: SRSP Relatives (conditional table) -->
  <section class="mb-8">
    <div class="flex items-center gap-4 mb-4">
      <span class="font-medium">Do you have a relative working at SRSP?</span>
      <label class="flex items-center gap-2">
        <input type="radio" v-model="form.has_srsp_relative" :value="true" /> Yes
      </label>
      <label class="flex items-center gap-2">
        <input type="radio" v-model="form.has_srsp_relative" :value="false" /> No
      </label>
    </div>

    <div v-if="form.has_srsp_relative">
      <div v-for="(rel, i) in form.srsp_relatives" :key="i"
           class="flex gap-3 mb-3">
        <input v-model="rel.name" placeholder="Full Name"
               class="border rounded p-2 flex-1" />
        <input v-model="rel.position" placeholder="Position"
               class="border rounded p-2 flex-1" />
        <input v-model="rel.office" placeholder="Office"
               class="border rounded p-2 flex-1" />
        <button @click="removeRelative(i)" class="text-red-500">✕</button>
      </div>
      <button type="button" @click="addRelative"
              class="text-blue-600 text-sm hover:underline">
        + Add Relative
      </button>
    </div>
  </section>
</template>
```

---

## Part 8: Lab 4 — Admin Report Table with Filters

```vue
<!-- File: src/views/AdminApplicantsReport.vue (abbreviated) -->
<script setup>
import { ref, watchEffect } from 'vue'
import adminApi from '../api/adminClient'
import { usePagination } from '../composables/usePagination'

const { page, perPage, total, totalPages, hasNext, hasPrev, setPage, setTotal } = usePagination(20)

const filters = ref({
  search: '',
  district: '',
  sector: '',
  status: '',
  gender: '',
  doc_status: '',
  sort_by: 'created_at',
  sort_dir: 'desc',
})

const applicants = ref([])
const loading = ref(false)
const filterOptions = ref({ districts: [], sectors: [], statuses: [] })

// Load filter options once
async function loadFilterOptions() {
  const { data } = await adminApi.get('/admin/reports/filter-options')
  filterOptions.value = data
}
loadFilterOptions()

// Auto-fetch when any filter or page changes
watchEffect(async () => {
  loading.value = true
  try {
    const { data } = await adminApi.get('/admin/applicants/report', {
      params: {
        page: page.value,
        per_page: perPage.value,
        ...filters.value,
      },
    })
    applicants.value = data.data
    setTotal(data.total)
  } catch (err) {
    console.error('Failed to load report:', err)
  } finally {
    loading.value = false
  }
})

function resetFilters() {
  filters.value = {
    search: '', district: '', sector: '', status: '',
    gender: '', doc_status: '', sort_by: 'created_at', sort_dir: 'desc',
  }
  setPage(1)
}
</script>

<template>
  <div>
    <!-- Filters -->
    <div class="bg-white rounded-xl shadow p-4 mb-4 flex flex-wrap gap-3">
      <input v-model="filters.search" placeholder="Search name, CNIC, email..."
             class="border rounded p-2 text-sm" @input="setPage(1)" />

      <select v-model="filters.district" class="border rounded p-2 text-sm"
              @change="setPage(1)">
        <option value="">All Districts</option>
        <option v-for="d in filterOptions.districts" :key="d" :value="d">{{ d }}</option>
      </select>

      <select v-model="filters.status" class="border rounded p-2 text-sm"
              @change="setPage(1)">
        <option value="">All Statuses</option>
        <option value="Eligible">Eligible</option>
        <option value="Ineligible">Ineligible</option>
        <option value="Decision Pending">Decision Pending</option>
      </select>

      <button @click="resetFilters" class="text-sm text-blue-600 hover:underline">
        Reset
      </button>
    </div>

    <!-- Table -->
    <div class="bg-white rounded-xl shadow overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50">
          <tr>
            <th class="p-3 text-left">Name</th>
            <th class="p-3 text-left">CNIC</th>
            <th class="p-3 text-left">District</th>
            <th class="p-3 text-left">Status</th>
            <th class="p-3 text-left">Joined</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="5" class="text-center py-8 text-gray-400">Loading...</td>
          </tr>
          <tr v-else-if="applicants.length === 0">
            <td colspan="5" class="text-center py-8 text-gray-400">No results</td>
          </tr>
          <tr v-else v-for="a in applicants" :key="a.user_id"
              class="border-t hover:bg-gray-50">
            <td class="p-3">{{ a.first_name }} {{ a.last_name }}</td>
            <td class="p-3 font-mono text-xs">{{ a.cnic }}</td>
            <td class="p-3">{{ a.business_location_district || '—' }}</td>
            <td class="p-3">
              <span :class="{
                'text-green-600': a.applicant_status === 'Eligible',
                'text-red-600': a.applicant_status === 'Ineligible',
                'text-yellow-600': a.applicant_status === 'Decision Pending',
              }">
                {{ a.applicant_status || 'Pending' }}
              </span>
            </td>
            <td class="p-3 text-xs text-gray-500">
              {{ new Date(a.created_at).toLocaleDateString() }}
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="flex items-center justify-between p-4 border-t">
        <span class="text-sm text-gray-500">
          {{ total }} total applicants
        </span>
        <div class="flex gap-2">
          <button @click="setPage(page - 1)" :disabled="!hasPrev"
                  class="px-3 py-1 border rounded text-sm disabled:opacity-40">
            Previous
          </button>
          <span class="px-3 py-1 text-sm">{{ page }} / {{ totalPages }}</span>
          <button @click="setPage(page + 1)" :disabled="!hasNext"
                  class="px-3 py-1 border rounded text-sm disabled:opacity-40">
            Next
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
```

---

## Part 9: Chart.js Admin Dashboard

```vue
<!-- File: src/views/AdminDashboard.vue (chart section) -->
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Chart, registerables } from 'chart.js'
import adminApi from '../api/adminClient'

Chart.register(...registerables)

const chartCanvas = ref(null)
let chartInstance = null

const stats = ref({
  total_users: 0,
  total_businesses: 0,
  total_grants: 0,
  approved: 0,
  hfc_pending: 0,
})

const timeRange = ref('week') // 'week' | 'month' | 'all'

async function loadStats() {
  const { data } = await adminApi.get('/admin/reports/dashboard-stats')
  stats.value = data
}

async function loadChart() {
  const { data } = await adminApi.get('/admin/reports/dashboard-frequency', {
    params: { range: timeRange.value }
  })

  if (chartInstance) chartInstance.destroy()

  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: [
        {
          label: 'Registrations',
          data: data.registrations,
          borderColor: '#3b82f6',
          tension: 0.3,
          fill: false,
        },
        {
          label: 'Grant Applications',
          data: data.applications,
          borderColor: '#10b981',
          tension: 0.3,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'top' },
        title: { display: true, text: 'Registration & Application Trend' },
      },
      scales: {
        y: { beginAtZero: true },
      },
    },
  })
}

onMounted(async () => {
  await Promise.all([loadStats(), loadChart()])
})

onUnmounted(() => {
  if (chartInstance) chartInstance.destroy()
})
</script>

<template>
  <div class="p-6">
    <!-- Stats Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
      <div class="bg-white rounded-xl shadow p-4 text-center">
        <div data-cy="stat-total-users" class="text-3xl font-bold text-blue-600">
          {{ stats.total_users }}
        </div>
        <div class="text-sm text-gray-500 mt-1">Total Registrations</div>
      </div>
      <div class="bg-white rounded-xl shadow p-4 text-center">
        <div class="text-3xl font-bold text-green-600">{{ stats.total_businesses }}</div>
        <div class="text-sm text-gray-500 mt-1">Business Profiles</div>
      </div>
      <div class="bg-white rounded-xl shadow p-4 text-center">
        <div class="text-3xl font-bold text-purple-600">{{ stats.total_grants }}</div>
        <div class="text-sm text-gray-500 mt-1">Grant Applications</div>
      </div>
      <div class="bg-white rounded-xl shadow p-4 text-center">
        <div data-cy="stat-approved" class="text-3xl font-bold text-emerald-600">
          {{ stats.approved }}
        </div>
        <div class="text-sm text-gray-500 mt-1">Approved</div>
      </div>
      <div class="bg-white rounded-xl shadow p-4 text-center">
        <div class="text-3xl font-bold text-yellow-600">{{ stats.hfc_pending }}</div>
        <div class="text-sm text-gray-500 mt-1">HFC Pending</div>
      </div>
    </div>

    <!-- Time Range Selector -->
    <div class="flex gap-2 mb-4">
      <button v-for="r in ['week', 'month', 'all']" :key="r"
              @click="timeRange = r; loadChart()"
              :class="timeRange === r ? 'bg-blue-600 text-white' : 'bg-white text-gray-600'"
              class="px-4 py-1.5 rounded border text-sm">
        {{ r }}
      </button>
    </div>

    <!-- Chart -->
    <div class="bg-white rounded-xl shadow p-6">
      <canvas ref="chartCanvas" height="100"></canvas>
    </div>
  </div>
</template>
```

---

## Part 10: Component Testing with Vitest

```bash
npm install --save-dev vitest @vue/test-utils jsdom @vitejs/plugin-vue
```

```javascript
// File: vite.config.js — add test config
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

### Testing the Login Component

```javascript
// File: src/views/__tests__/UserLogin.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import UserLogin from '../UserLogin.vue'

// Mock the API client
vi.mock('../../api/client', () => ({
  default: {
    post: vi.fn(),
  },
}))

import api from '../../api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: UserLogin },
    { path: '/dashboard', component: { template: '<div>Dashboard</div>' } },
  ],
})

describe('UserLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders login heading', () => {
    const wrapper = mount(UserLogin, {
      global: { plugins: [router] },
    })
    expect(wrapper.find('[data-cy="login-heading"]').text()).toContain('Login')
  })

  it('stores token on successful login', async () => {
    api.post.mockResolvedValueOnce({
      data: { token: 'test-token', user_id: 1, language: 'english' },
    })

    const wrapper = mount(UserLogin, {
      global: { plugins: [router] },
    })

    await wrapper.find('[data-cy="email-input"]').setValue('test@example.com')
    await wrapper.find('[data-cy="password-input"]').setValue('password')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(localStorage.getItem('userToken')).toBe('test-token')
    })
  })

  it('shows error on failed login', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 401 } })

    const wrapper = mount(UserLogin, {
      global: { plugins: [router] },
    })

    await wrapper.find('[data-cy="email-input"]').setValue('bad@example.com')
    await wrapper.find('[data-cy="password-input"]').setValue('wrong')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(wrapper.find('[data-cy="error-message"]').exists()).toBe(true)
    })
  })

  it('shows Urdu heading when language is urdu', () => {
    localStorage.setItem('language', 'urdu')
    const wrapper = mount(UserLogin, {
      global: { plugins: [router] },
    })
    expect(wrapper.find('[data-cy="login-heading"]').text()).toContain('لاگ ان')
  })
})
```

---

## Part 11: Git Workflow for the Portal

### Branching Conventions

```
main            production-ready code
develop         integration branch
feature/*       one branch per portal feature
bugfix/*        bug fixes against develop
hotfix/*        emergency fixes against main
release/*       release preparation branches
```

### Feature Branch to Merge — Full Walkthrough

```bash
# Start new feature
git checkout develop
git pull origin develop
git checkout -b feature/hfc-admin-dashboard

# Work on the feature — multiple commits
git add internal/hfc/admin_handler.go
git commit -m "Add HFC admin dashboard stats endpoint"

git add frontend/src/views/AdminHfcDashboard.vue
git commit -m "Add Vue HFC admin dashboard component"

git add internal/hfc/admin_handler_test.go
git commit -m "Add tests for HFC dashboard handler"

# Prepare to merge — rebase onto latest develop
git fetch origin
git rebase origin/develop

# Fix conflicts if any
# git add <conflicted files>
# git rebase --continue

# Push and open PR
git push origin feature/hfc-admin-dashboard

# After PR is approved, merge
git checkout develop
git merge --no-ff feature/hfc-admin-dashboard -m "Merge feature/hfc-admin-dashboard"
git branch -d feature/hfc-admin-dashboard
```

### Semantic Commit Convention

```bash
# New feature
git commit -m "feat: add whitelist gate to grant submission endpoint"

# Bug fix
git commit -m "fix: return [] instead of null for empty updates list"

# Tests
git commit -m "test: add table-driven tests for HFC scoring rules"

# Refactor
git commit -m "refactor: extract whitelist check into AccessChecker service"

# Docs
git commit -m "docs: document HFC scoring rules in CLAUDE.md"

# Chore (build, deps, config)
git commit -m "chore: add golang-migrate dependency"
```

### Conflict Resolution Practice

1. Create two branches from `main` that both add a route to `router/index.js`.
2. Merge the first branch.
3. Try to merge the second branch — conflict appears.
4. Open the file, see the conflict markers:

```
<<<<<<< HEAD
  { path: '/grant-review', component: () => import('../views/SmeGrantReview.vue') },
=======
  { path: '/grant-status', component: () => import('../views/GrantStatus.vue') },
>>>>>>> feature/grant-status
```

5. Keep both routes (they are not exclusive):

```javascript
  { path: '/grant-review', component: () => import('../views/SmeGrantReview.vue') },
  { path: '/grant-status', component: () => import('../views/GrantStatus.vue') },
```

6. Stage and commit:

```bash
git add frontend/src/router/index.js
git commit -m "Merge feature/grant-status — keep both new routes"
```

---

## Part 12: Deploying Vue to nginx

```bash
# Build for production
cd frontend
npm run build
# Output: frontend/dist/

# The Dockerfile.frontend handles this automatically
docker compose build frontend
docker compose up -d frontend
```

### Environment Variables in Vite

Vite bakes environment variables into the bundle at build time. Use `VITE_` prefix:

```bash
# .env.production
VITE_API_BASE_URL=/api
```

```javascript
// Access in code
const baseURL = import.meta.env.VITE_API_BASE_URL
```

Pass at Docker build time:

```bash
docker build \
  --build-arg VITE_API_BASE_URL=/api \
  -t peace-sme-frontend:v0.1.0 \
  frontend/
```

---

## Capstone Lab: Full User Story

Trace every layer of this user story:

**"A grant officer (admin) logs in, searches for Ahmed Khan's application, marks Ahmed as Eligible, whitelists him for grant submission, Ahmed then logs in and submits a grant, and the HFC score appears in the admin queue."**

| Step | Vue route | API call | Go handler | Service | Repository | DB table | Git commit |
|---|---|---|---|---|---|---|---|
| Admin login | `/admin/login` | `POST /api/admin/login` | `auth.AdminLogin` | `VerifyAdminPassword` | — | — | `feat: admin login` |
| Search Ahmed | `/admin/applicants/report` | `GET /api/admin/applicants/report?search=Ahmed` | `report.ApplicantReport` | `FilterApplicants` | `ApplicantRepository.Report` | users, businesses | `feat: applicant report` |
| Mark Eligible | `/admin/applicant-status` | `POST /api/admin/applicant-status` | `status.Upsert` | `UpsertStatus` | `StatusRepository.Upsert` | applicant_status | `feat: applicant status` |
| Whitelist Ahmed | `/admin/user-access` | `POST /api/admin/grants/access` | `grant.SetAccess` | `UpsertWhitelist` | `WhitelistRepository.Upsert` | grant_access_whitelist | `feat: grant whitelist` |
| Ahmed logs in | `/login` | `POST /api/login` | `user.Login` | `VerifyLogin` | `UserRepository.FindByEmail` | users | `feat: user login` |
| Submit grant | `/grant-application` | `POST /api/grant` | `grant.Submit` | `CreateGrant` | `GrantRepository.Insert` | grants | `feat: grant submission` |
| HFC job runs | (background) | (internal) | (worker) | `CalculateScore` | `HFCRepository.Upsert` | hfc_evaluations, grants | `feat: hfc scoring` |
| Admin sees HFC | `/admin/hfc/queue` | `GET /api/admin/hfc/queue` | `hfc.Queue` | `GetQueue` | `HFCRepository.Queue` | grants, hfc_evaluations | `feat: hfc queue` |

This trace is the real learning loop. Every button click touches 7 layers.

---

## Mastery Check

You understand this chapter when you can answer:

1. What is the difference between `ref` and `reactive`? Give an example where using `reactive` for a string would cause a bug.
2. Write a composable `useGrantAccess` that calls `GET /api/grant` on mount, returns the `access_state` field as a computed property, and exposes a `canSubmit` boolean that is true only when `access_state === 'selected'` or `access_state === 'not_required'`.
3. The Axios response interceptor catches 401 and redirects to `/login`. What problem does this solve, and what problem could it create for the admin pages?
4. Your colleague pushes code that changes the API response field from `update_id` to `id`. The Vue admin dashboard breaks silently — the dashboard still renders, but all `update.update_id` references show `undefined`. How would a contract test have caught this before deployment?
5. Walk through the Git commands for creating a hotfix, tagging it, and back-merging it to both `main` and `develop`.
