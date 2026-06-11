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

## Mastery Check

You understand this chapter when you can:
- Build a large form without losing state.
- Create reusable admin table controls.
- Keep Vue labels bilingual.
- Connect every screen to the matching `/api` endpoint.
- Handle loading, error, empty, and success states professionally.
