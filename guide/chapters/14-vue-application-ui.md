# Chapter 14: Vue Applicant and Admin Interfaces

## Purpose

This chapter turns Vue fundamentals into full application screens.

## Theoretical Background

### Form State Management (Wizard Pattern)
Large multi-step forms (like the 9-section Grant Application form) require strict state management:
- **Single Source of Truth:** Keep form data in a single, root-level reactive object (`reactive()`). This avoids syncing child component state manually.
- **Wizard Flow Patterns:** Break the layout into steps. A reactive `currentStep` index determines which section renders (`v-if="currentStep === X"`).
- **Validation Gates:** Before allowing a user to progress to the next step, execute validation logic on the subfields of the current step.
- **Dirty Checking:** Track if the user has modified fields without saving, allowing you to prompt a warning before they close the tab or navigate away.

### Chart Rendering and Component Cleanup
When rendering visualizations (like frequency reports or risk distributions) using Canvas-based libraries (Chart.js):
- Canvas rendering requires a physical DOM node to exist on the page. Therefore, chart initialization must take place inside the `onMounted()` hook.
- **Preventing Memory Leaks:** If a user navigates to another page, the component is unmounted but the chart instance may still exist in heap memory. Always store a reference to the chart instance and destroy it in the `onBeforeUnmount()` lifecycle hook.

### External Resources
- [Vue.js State Management Guide](https://vuejs.org/guide/scaling-up/state-management.html)
- [Chart.js Integration with Vue](https://www.chartjs.org/docs/latest/getting-started/integration.html)

---

## Public Views

Build:
- Landing page with updates and FAQ access.
- Language selection.
- Terms and conditions.
- Registration form.
- User login.
- Admin login.
- Waiting room.
- Geo-blocked page.
- Password reset disabled pages.

---

## Applicant Views

Build:
- Dashboard.
- Business profile form.
- Grant application form.
- Grant review page.
- Upload flows for documents and media.

The grant form is large. Split it into sections:
1. Applicant identification.
2. Business details.
3. Purpose of grant.
4. Items to be financed.
5. Contribution.
6. Business growth.
7. Disclaimer.
8. Declaration.
9. How did you hear.

Use child components when a section has independent state and validation.

---

## Admin Views

Build:
- Admin dashboard.
- Submitted grants table.
- Grant detail.
- Applicant status.
- Grant access whitelist.
- Applicant report.
- Applied details report.
- Approved grants report.
- Missing documents report.
- Eligibility criteria report.
- Full report.
- HFC dashboard, queue, applicant detail, model tuning.
- Updates management.
- FAQ management.
- Database browser.

---

## Form State Pattern

Use:

```js
const form = reactive({
  grant_required: null,
  financed_items: [],
  declaration_accepted: false
})
```

For repeating rows:

```js
function addItem() {
  form.financed_items.push({ item: '', quantity: 1, estimated_cost: null })
}
```

---

## Admin Tables

Tables need:
- loading state
- error state
- empty state
- pagination controls
- sortable headers
- filters
- CSV export action where supported

Keep query state in the URL when useful so admins can refresh or share filtered views.

---

## Charts

Use Chart.js for:
- dashboard counts
- registration/application frequency
- HFC status distribution
- eligibility criteria breakdown

Charts should be backed by API responses, not hardcoded data.

---

## Practical Examples

### Example: Multi-step Wizard Form with Validation and State
This example demonstrates a complete Vue component layout implementing a multi-step form wizard with inline step validation and repeating row creation:

```vue
<!-- File: src/components/GrantWizard.vue -->
<script setup>
import { ref, reactive, computed } from 'vue'

const currentStep = ref(1)

// Root Single Source of Truth form state
const form = reactive({
  applicantName: '',
  financedItems: [
    { name: '', qty: 1, cost: 0 }
  ]
})

// Validation per step
const stepErrors = ref([])

const isStepValid = () => {
  stepErrors.value = []
  
  if (currentStep.value === 1) {
    if (!form.applicantName.trim()) {
      stepErrors.value.push('Applicant name is required.')
    }
  }
  
  if (currentStep.value === 2) {
    if (form.financedItems.length === 0) {
      stepErrors.value.push('At least one item must be added.')
    }
    for (let i = 0; i < form.financedItems.length; i++) {
      if (!form.financedItems[i].name.trim() || form.financedItems[i].cost <= 0) {
        stepErrors.value.push(`Item ${i + 1} has invalid name or estimated cost.`)
      }
    }
  }

  return stepErrors.value.length === 0
}

const nextStep = () => {
  if (isStepValid()) {
    currentStep.value++
  }
}

const prevStep = () => {
  currentStep.value--
}

// Add/Remove repeating item rows
const addRow = () => {
  form.financedItems.push({ name: '', qty: 1, cost: 0 })
}

const removeRow = (index) => {
  form.financedItems.splice(index, 1)
}

// Compute total requested cost
const totalCost = computed(() => {
  return form.financedItems.reduce((sum, item) => sum + (item.qty * item.cost), 0)
})

const submitForm = () => {
  if (isStepValid()) {
    console.log('Submitting payload to /api/grant:', form)
    // api.post('/api/grant', form) ...
  }
}
</script>

<template>
  <div class="max-w-xl mx-auto p-8 bg-white border border-slate-200 rounded-xl shadow-lg">
    <!-- Step Indicators -->
    <div class="flex items-center justify-between mb-8">
      <span :class="['font-bold', currentStep >= 1 ? 'text-blue-600' : 'text-slate-400']">1. Identity</span>
      <span class="w-12 h-0.5 bg-slate-300"></span>
      <span :class="['font-bold', currentStep >= 2 ? 'text-blue-600' : 'text-slate-400']">2. Financed Items</span>
    </div>

    <!-- Validation Warnings -->
    <div v-if="stepErrors.length > 0" class="mb-6 p-4 bg-red-50 border-l-4 border-red-500 text-red-700">
      <ul>
        <li v-for="err in stepErrors" :key="err" class="text-sm">{{ err }}</li>
      </ul>
    </div>

    <!-- Step 1 View -->
    <div v-if="currentStep === 1" class="space-y-4">
      <label class="block text-sm font-semibold text-slate-700">Full Name of Applicant</label>
      <input 
        v-model="form.applicantName" 
        type="text" 
        class="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
      />
    </div>

    <!-- Step 2 View -->
    <div v-if="currentStep === 2" class="space-y-4">
      <h3 class="text-lg font-bold text-slate-800">Items to be Financed</h3>
      
      <div v-for="(item, idx) in form.financedItems" :key="idx" class="flex gap-4 items-center">
        <input 
          v-model="item.name" 
          placeholder="Item name"
          class="flex-1 px-3 py-2 border rounded-md"
        />
        <input 
          v-model.number="item.qty" 
          type="number"
          placeholder="Qty"
          class="w-16 px-3 py-2 border rounded-md"
        />
        <input 
          v-model.number="item.cost" 
          type="number"
          placeholder="Cost"
          class="w-24 px-3 py-2 border rounded-md"
        />
        <button 
          @click="removeRow(idx)" 
          class="text-red-500 font-bold hover:text-red-700"
        >
          &times;
        </button>
      </div>

      <button 
        @click="addRow" 
        class="text-sm text-blue-600 hover:underline"
      >
        + Add Another Item
      </button>

      <div class="pt-4 border-t text-right font-bold text-slate-800">
        Total Estimated Cost: ${{ totalCost }}
      </div>
    </div>

    <!-- Navigation Buttons -->
    <div class="mt-8 flex justify-between">
      <button 
        v-if="currentStep > 1" 
        @click="prevStep" 
        class="px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-lg"
      >
        Back
      </button>
      <div class="ml-auto">
        <button 
          v-if="currentStep < 2" 
          @click="nextStep" 
          class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
        >
          Next
        </button>
        <button 
          v-else 
          @click="submitForm" 
          class="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg"
        >
          Submit Application
        </button>
      </div>
    </div>
  </div>
</template>
```

---

## Complete Grant Application Form

The grant application is the most complex screen in the portal — 9 sections, JSONB arrays, dynamic rows, and a conditional disclaimer. Here is the complete implementation:

```vue
<!-- File: src/views/SmeGrantApplication.vue -->
<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { userApi } from '../api/client'
import { useLanguage } from '../composables/useLanguage'

const router = useRouter()
const { t, isRTL } = useLanguage()

const currentStep = ref(1)
const totalSteps = 9
const loading = ref(false)
const error = ref('')
const accessState = ref(null) // loaded from GET /api/grant

// ── Single source of truth for the entire form ────────────────────────────────
const form = reactive({
    // Section 1: Identification
    domicile_district: '',
    how_did_you_hear: '',

    // Section 3: Purpose
    expression_of_interest: [],
    other_purpose_text: '',
    working_capital: false,

    // Section 4: Business type
    business_type: [],
    business_type_other: '',
    tax_registration_status: [],
    ntn_registration_no: '',
    tax_filer_status: '',

    // Section 4: Items to finance
    financed_items: [{ item: '', quantity: 1, estimated_cost: 0 }],

    // Section 5: Contribution
    contribution_type: '',
    financial_amount: null,
    financial_amount_words: '',
    inkind_details: '',
    inkind_value: null,
    inkind_value_words: '',
    contribution_utilization: '',

    // Section 6: Growth
    grant_support_growth: '',
    expected_production_increase: '',
    employment_grid: {},

    // Section 7: Grant amount
    grant_required: null,
    grant_amount_words: '',

    // Section 8: Disclaimer
    has_srsp_relative: false,
    srsp_relatives: [],

    // Section 9: Declaration
    declaration_accepted: false,
    declaration_name: '',
    application_date: new Date().toISOString().split('T')[0],
})

// ── Computed validations ──────────────────────────────────────────────────────
const stepValid = computed(() => {
    switch (currentStep.value) {
        case 1: return !!form.domicile_district
        case 3: return form.expression_of_interest.length > 0 || form.working_capital
        case 4: return form.financed_items.every(i => i.item && i.quantity > 0 && i.estimated_cost > 0)
        case 7: return form.grant_required > 0 && !!form.grant_amount_words
        case 9: return form.declaration_accepted && !!form.declaration_name
        default: return true
    }
})

// ── Load access state on mount ────────────────────────────────────────────────
onMounted(async () => {
    try {
        const { data } = await userApi.get('/grant')
        accessState.value = data
        if (data.exists) {
            // Grant already submitted — redirect to review page
            router.push('/grant-review')
        }
        if (!data.can_apply) {
            error.value = data.reason_message || 'You are not currently eligible to apply.'
        }
    } catch {
        error.value = 'Failed to load grant access status.'
    }
})

// ── Dynamic rows ──────────────────────────────────────────────────────────────
function addFinancedItem() {
    form.financed_items.push({ item: '', quantity: 1, estimated_cost: 0 })
}

function removeFinancedItem(index) {
    if (form.financed_items.length > 1) {
        form.financed_items.splice(index, 1)
    }
}

function addSRSPRelative() {
    form.srsp_relatives.push({ name: '', position: '', office: '' })
}

function removeSRSPRelative(index) {
    form.srsp_relatives.splice(index, 1)
}

// ── Total cost computed ───────────────────────────────────────────────────────
const totalFinancedCost = computed(() =>
    form.financed_items.reduce((sum, i) => sum + (i.quantity * i.estimated_cost), 0)
)

// ── Submit ────────────────────────────────────────────────────────────────────
async function submitApplication() {
    if (!stepValid.value) return
    loading.value = true
    error.value = ''
    try {
        await userApi.post('/grant', form)
        router.push('/grant-review')
    } catch (err) {
        error.value = err.response?.data?.message || 'Submission failed. Please try again.'
    } finally {
        loading.value = false
    }
}
</script>

<template>
  <div :dir="isRTL ? 'rtl' : 'ltr'" class="max-w-3xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Grant Application</h1>

    <!-- Access blocked -->
    <div v-if="error" class="p-4 bg-red-50 border border-red-300 rounded-lg text-red-700 mb-6">
      {{ error }}
    </div>

    <!-- Step progress bar -->
    <div class="flex gap-1 mb-8">
      <div
        v-for="n in totalSteps" :key="n"
        :class="['h-2 flex-1 rounded', n <= currentStep ? 'bg-blue-600' : 'bg-slate-200']"
      />
    </div>

    <!-- Section 1: Identification -->
    <div v-if="currentStep === 1" class="space-y-4">
      <h2 class="text-lg font-semibold">Section 1: Identification</h2>
      <select v-model="form.domicile_district" class="w-full border rounded-lg px-3 py-2">
        <option value="">Select District</option>
        <option>Swat</option>
        <option>Shangla</option>
        <option>Upper Dir</option>
        <option>Upper Chitral</option>
        <option>Lower Chitral</option>
      </select>
    </div>

    <!-- Section 4: Financed Items -->
    <div v-if="currentStep === 4" class="space-y-4">
      <h2 class="text-lg font-semibold">Section 4: Items to be Financed</h2>
      <div v-for="(item, idx) in form.financed_items" :key="idx"
           class="grid grid-cols-4 gap-3 items-center">
        <input v-model="item.item" placeholder="Item name"
               class="col-span-2 border rounded-lg px-3 py-2" />
        <input v-model.number="item.quantity" type="number" placeholder="Qty"
               class="border rounded-lg px-3 py-2" />
        <input v-model.number="item.estimated_cost" type="number" placeholder="PKR"
               class="border rounded-lg px-3 py-2" />
        <button @click="removeFinancedItem(idx)"
                class="text-red-500 font-bold text-xl col-start-5">&times;</button>
      </div>
      <button @click="addFinancedItem" class="text-sm text-blue-600 hover:underline">
        + Add Item
      </button>
      <p class="text-right font-semibold">Total: PKR {{ totalFinancedCost.toLocaleString() }}</p>
    </div>

    <!-- Section 8: SRSP Relatives -->
    <div v-if="currentStep === 8" class="space-y-4">
      <h2 class="text-lg font-semibold">Section 8: Disclaimer</h2>
      <label class="flex items-center gap-3">
        <input type="checkbox" v-model="form.has_srsp_relative" class="w-4 h-4" />
        <span>Do you have a relative working in SRSP?</span>
      </label>
      <div v-if="form.has_srsp_relative" class="mt-4 space-y-3">
        <div v-for="(rel, idx) in form.srsp_relatives" :key="idx"
             class="grid grid-cols-3 gap-3">
          <input v-model="rel.name" placeholder="Full name" class="border rounded-lg px-3 py-2" />
          <input v-model="rel.position" placeholder="Position" class="border rounded-lg px-3 py-2" />
          <input v-model="rel.office" placeholder="Office" class="border rounded-lg px-3 py-2" />
        </div>
        <button @click="addSRSPRelative" class="text-sm text-blue-600 hover:underline">
          + Add Relative
        </button>
      </div>
    </div>

    <!-- Navigation -->
    <div class="flex justify-between mt-8">
      <button v-if="currentStep > 1" @click="currentStep--"
              class="px-4 py-2 bg-slate-100 rounded-lg hover:bg-slate-200">
        Back
      </button>
      <button v-if="currentStep < totalSteps" @click="if (stepValid) currentStep++"
              :disabled="!stepValid"
              class="ml-auto px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
        Next
      </button>
      <button v-else @click="submitApplication"
              :disabled="loading || !stepValid"
              class="ml-auto px-5 py-2 bg-emerald-600 text-white rounded-lg disabled:opacity-50">
        {{ loading ? 'Submitting...' : 'Submit Application' }}
      </button>
    </div>
  </div>
</template>
```

---

## Admin Dashboard with Charts

```vue
<!-- File: src/views/admin/AdminDashboard.vue -->
<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { adminApi } from '../../api/client'
import Chart from 'chart.js/auto'

const stats = ref(null)
const loading = ref(true)
let frequencyChart = null   // store reference to destroy on unmount

onMounted(async () => {
    // Load summary stats
    const { data } = await adminApi.get('/admin/dashboard/stats')
    stats.value = data
    loading.value = false

    // Load frequency data for chart
    const { data: freq } = await adminApi.get('/admin/dashboard/frequency', {
        params: { interval: 'daily' }
    })

    // Initialize Chart.js — must happen after DOM renders (onMounted)
    const ctx = document.getElementById('registrationChart')
    if (ctx) {
        frequencyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: freq.map(d => d.date),
                datasets: [{
                    label: 'Registrations',
                    data: freq.map(d => d.count),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59,130,246,0.1)',
                    fill: true,
                    tension: 0.4,
                }]
            },
            options: { responsive: true, plugins: { legend: { display: false } } }
        })
    }
})

// Destroy chart instance to prevent memory leaks when navigating away
onBeforeUnmount(() => {
    if (frequencyChart) {
        frequencyChart.destroy()
        frequencyChart = null
    }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-2xl font-bold text-white">Admin Dashboard</h1>

    <!-- Stats cards -->
    <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-slate-800 rounded-xl p-4 text-center">
        <p class="text-3xl font-bold text-blue-400">{{ stats.total_users }}</p>
        <p class="text-slate-400 text-sm mt-1">Total Applicants</p>
      </div>
      <div class="bg-slate-800 rounded-xl p-4 text-center">
        <p class="text-3xl font-bold text-emerald-400">{{ stats.total_grants }}</p>
        <p class="text-slate-400 text-sm mt-1">Grants Submitted</p>
      </div>
      <div class="bg-slate-800 rounded-xl p-4 text-center">
        <p class="text-3xl font-bold text-yellow-400">{{ stats.approved_count }}</p>
        <p class="text-slate-400 text-sm mt-1">Approved</p>
      </div>
      <div class="bg-slate-800 rounded-xl p-4 text-center">
        <p class="text-3xl font-bold text-red-400">{{ stats.hfc_pending }}</p>
        <p class="text-slate-400 text-sm mt-1">HFC Pending</p>
      </div>
    </div>

    <!-- Registration frequency chart -->
    <div class="bg-slate-800 rounded-xl p-6">
      <h2 class="text-lg font-semibold text-white mb-4">Registration Frequency</h2>
      <canvas id="registrationChart" height="80"></canvas>
    </div>
  </div>
</template>
```

---

## Admin Applicants Table with Pagination and Filters

```vue
<!-- File: src/views/admin/AdminApplicants.vue -->
<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { adminApi } from '../../api/client'
import { usePagination } from '../../composables/usePagination'

// Set up paginated data loading
const filters = reactive({
    search: '',
    district: '',
    status: '',
    sort_by: 'created_at',
    sort_dir: 'desc',
})

const { page, items, total, loading, error, load, goTo } = usePagination(
    (params) => adminApi.get('/admin/applicants/report', { params }),
    20
)

// Reload when filters change (reset to page 1)
watch(filters, () => {
    page.value = 1
    load(filters)
}, { deep: true })

onMounted(() => load(filters))

// CSV export using short-lived query token
async function exportCSV() {
    // Get a short-lived query token first
    const { data } = await adminApi.get('/admin/reports/full-applicant-profiles')
    // The token is in the Authorization header query param for direct browser download
    window.open(`http://localhost:5000/api/admin/reports/full-applicant-profiles/csv?token=${data.token}`)
}
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-white">Applicants</h1>
      <button @click="exportCSV"
              class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm">
        Export CSV
      </button>
    </div>

    <!-- Filters bar -->
    <div class="flex gap-3 mb-6 flex-wrap">
      <input v-model="filters.search" placeholder="Search name, email, CNIC..."
             class="border border-slate-600 bg-slate-800 text-white px-3 py-2 rounded-lg text-sm" />
      <select v-model="filters.district"
              class="border border-slate-600 bg-slate-800 text-white px-3 py-2 rounded-lg text-sm">
        <option value="">All Districts</option>
        <option>Swat</option><option>Shangla</option>
        <option>Upper Dir</option><option>Upper Chitral</option><option>Lower Chitral</option>
      </select>
      <select v-model="filters.status"
              class="border border-slate-600 bg-slate-800 text-white px-3 py-2 rounded-lg text-sm">
        <option value="">All Status</option>
        <option>Pending</option><option>Approved</option><option>Rejected</option>
      </select>
    </div>

    <!-- Loading / error / empty states -->
    <div v-if="loading" class="text-center text-slate-400 py-12">Loading...</div>
    <div v-else-if="error" class="text-red-400 py-4">{{ error }}</div>
    <div v-else-if="items.length === 0" class="text-center text-slate-500 py-12">
      No applicants match the current filters.
    </div>

    <!-- Data table -->
    <table v-else class="w-full text-sm text-left text-slate-300">
      <thead class="text-xs uppercase text-slate-500 border-b border-slate-700">
        <tr>
          <th class="pb-3">Name</th>
          <th class="pb-3">CNIC</th>
          <th class="pb-3">District</th>
          <th class="pb-3">Status</th>
          <th class="pb-3">Applied</th>
          <th class="pb-3"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in items" :key="a.user_id"
            class="border-b border-slate-800 hover:bg-slate-800/50">
          <td class="py-3">{{ a.first_name }} {{ a.last_name }}</td>
          <td class="py-3 font-mono">{{ a.cnic }}</td>
          <td class="py-3">{{ a.business_location_district || '—' }}</td>
          <td class="py-3">
            <span :class="[
              'px-2 py-0.5 rounded text-xs font-semibold',
              a.status === 'Approved' ? 'bg-emerald-900 text-emerald-300' :
              a.status === 'Rejected' ? 'bg-red-900 text-red-300' :
              'bg-yellow-900 text-yellow-300'
            ]">{{ a.status || 'Pending' }}</span>
          </td>
          <td class="py-3 text-slate-500">{{ a.created_at?.slice(0, 10) }}</td>
          <td class="py-3">
            <router-link :to="`/admin/applicants/${a.user_id}`"
                         class="text-blue-400 hover:underline text-xs">View</router-link>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Pagination -->
    <div class="flex items-center justify-between mt-6 text-sm text-slate-400">
      <span>{{ total }} total applicants</span>
      <div class="flex gap-2">
        <button @click="goTo(page - 1)" :disabled="page <= 1"
                class="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Prev</button>
        <span class="px-3 py-1">Page {{ page }}</span>
        <button @click="goTo(page + 1)" :disabled="items.length < 20"
                class="px-3 py-1 bg-slate-700 rounded disabled:opacity-40">Next</button>
      </div>
    </div>
  </div>
</template>
```

---

## Mastery Check

You understand this chapter when you can:
- Build a 9-step grant wizard that keeps all form state in a single `reactive()` object.
- Implement step validation gates using `computed()` that block navigation to the next step.
- Use `v-for` with `.splice()` and `.push()` to manage dynamic rows (financed items, SRSP relatives).
- Initialize a Chart.js chart in `onMounted()` and destroy it in `onBeforeUnmount()`.
- Wire an admin table to the `usePagination` composable and connect filters with `watch`.
- Handle loading, error, and empty states in every data-dependent component.
- Connect the grant form to `POST /api/grant` and redirect to the review page on success.
