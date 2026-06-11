# Chapter 19: Vue and Git Practice Lab

## Purpose

This lab makes Vue and Git practical. You will build frontend behavior that matches the Go API while using Git to protect every step.

## Vue Beginner Concepts by Portal Feature

| Vue concept | Portal feature | What you learn |
|---|---|---|
| `ref` | login email/password fields | single primitive reactive values |
| `reactive` | business profile form | object-shaped form state |
| `computed` | Urdu/English label selection | derived state |
| `watch` | filters triggering report reloads | reacting to changes |
| `onMounted` | fetch dashboard data | lifecycle fetching |
| props | reusable form input | parent-to-child data |
| emits | modal close, upload complete | child-to-parent events |
| router guards | protected dashboard/admin pages | client-side auth flow |
| composables | `useAuth`, `useLanguage`, `usePagination` | reusable stateful logic |
| Axios interceptors | bearer auth headers | API integration |

## Lab 1: Login Page

Theory:

- `ref` is best for simple values.
- `v-model` binds input value to state.
- submit handlers call API functions.

Portal task:

- build `UserLogin.vue`.
- call `POST /api/login`.
- store `userToken`.
- redirect to `/dashboard`.

Example:

```vue
<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function login() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.post('/login', {
      email_address: email.value,
      password: password.value,
    })
    localStorage.setItem('userToken', data.token)
    router.push('/dashboard')
  } catch (err) {
    error.value = 'Invalid login or blocked account'
  } finally {
    loading.value = false
  }
}
</script>
```

Git practice:

```bash
git checkout -b vue-user-login
git add frontend/src/views/UserLogin.vue
git commit -m "Add Vue user login page"
```

## Lab 2: Business Profile Form

Theory:

- `reactive` is useful for form objects.
- select inputs should store backend-compatible values.
- frontend validation improves UX, but backend validation remains authoritative.

Portal task:

- build `SmeBusinessProfile.vue`.
- fetch existing data with `GET /api/business`.
- create with `POST /api/business`.
- update with `PUT /api/business`.

State shape:

```js
const form = reactive({
  name_of_business: '',
  business_registration_number: '',
  business_location_district: '',
  business_sector: '',
  male_employees: 0,
  female_employees: 0,
})
```

Parallel Go task:

- `BusinessRequest` struct has matching JSON tags.
- Go validates allowed districts.
- repository uses `INSERT` or `UPDATE`.

Git practice:

```bash
git checkout -b vue-business-profile
git commit -m "Add business profile form state"
git commit -m "Connect business profile form to API"
```

## Lab 3: Grant Application Dynamic Sections

Theory:

- arrays in Vue are reactive when stored inside `reactive`.
- conditional rendering uses `v-if`.
- repeated rows use `v-for`.

Portal task:

- add financed item rows.
- show cash fields only when contribution includes cash.
- show in-kind fields only when contribution includes in-kind.
- show relatives table only when `has_srsp_relative` is true.

Example:

```js
function addFinancedItem() {
  form.financed_items.push({
    item: '',
    quantity: 1,
    estimated_cost: null,
  })
}
```

Parallel Go task:

- decode `financed_items` into `[]FinancedItem`.
- validate each row.
- store as JSONB.

Git practice:

```bash
git checkout -b vue-grant-form
git commit -m "Add grant financed items UI"
git commit -m "Add conditional grant contribution fields"
git commit -m "Connect grant form to API"
```

## Lab 4: Admin Report Table

Theory:

- tables need query state: page, per page, filters, sort.
- `watch` can reload data when filters change.
- query params should mirror backend filter names.

Portal task:

- build applicant report table.
- support `page`, `per_page`, `district`, `sector`, `status`, `search`, `sort_by`, `sort_dir`.

Parallel Go task:

- parse query params into `ApplicantReportFilter`.
- use SQL allow-list for sort fields.
- return `{data,total,page,per_page}`.

Git practice:

```bash
git checkout -b vue-admin-report
git commit -m "Add admin applicant report table"
git commit -m "Connect admin report filters"
```

## Git Lab: Learn by Reviewing Your Own Work

Before every commit:

```bash
git status
git diff
git add <files>
git diff --staged
git commit -m "Specific behavior"
```

Review questions:

- Did I include unrelated files?
- Did I accidentally commit generated output?
- Does the commit message describe behavior?
- Could this commit be reverted safely?
- Are tests or screenshots needed?

## Git Lab: Feature Branch to Merge

```bash
git checkout main
git checkout -b feature/grant-form
# build the feature
git add frontend/src/views/SmeGrantApplication.vue
git commit -m "Add grant application form"
git checkout main
git merge feature/grant-form
```

Conflict practice:

1. Create two branches that edit the same route list.
2. Merge one branch.
3. Merge the second branch.
4. Resolve the route conflict manually.
5. Run tests.
6. Commit the merge.

## Capstone Lab

Build one complete user story:

1. User logs in.
2. User opens dashboard.
3. User creates business profile.
4. Admin marks applicant eligible.
5. Admin whitelists user for grants.
6. User submits grant.
7. HFC score appears for admin.
8. Approver approves grant.

For every step, write down:

- Vue route.
- API endpoint.
- Go handler.
- Go service method.
- Repository query.
- Database table.
- Git commit.

This is the real learning loop. The concepts become durable when you can trace a button click all the way to SQL and back.

