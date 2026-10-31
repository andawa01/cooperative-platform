import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth, RequireRole } from '@/components/RequireAuth'
import { AppShell } from '@/components/layout/AppShell'
import { Loading } from '@/components/common/Loading'
import { AuthProvider } from '@/hooks/useAuth'

// Eagerly loaded: Login is the entry point for unauthenticated users.
import Login from '@/pages/Login'

// Lazy-loaded: each route becomes its own chunk, splitting the 777KB
// bundle into per-feature pieces that load on navigation.
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Account = lazy(() => import('@/pages/Account'))

const FarmersList = lazy(() => import('@/pages/Farmers/List'))
const NewFarmer = lazy(() => import('@/pages/Farmers/New'))
const FarmerDetail = lazy(() => import('@/pages/Farmers/Detail'))

const DeliveriesList = lazy(() => import('@/pages/Deliveries/List'))
const NewDelivery = lazy(() => import('@/pages/Deliveries/New'))
const DeliveryDetail = lazy(() => import('@/pages/Deliveries/Detail'))

const PaymentsList = lazy(() => import('@/pages/Payments/List'))
const NewPayment = lazy(() => import('@/pages/Payments/New'))
const PaymentDetail = lazy(() => import('@/pages/Payments/Detail'))

const NotificationsList = lazy(() => import('@/pages/Notifications/List'))
const NotificationDetail = lazy(() => import('@/pages/Notifications/Detail'))

const ProduceList = lazy(() => import('@/pages/Produce/List'))
const NewProduceLine = lazy(() => import('@/pages/Produce/New'))
const ProduceDetail = lazy(() => import('@/pages/Produce/Detail'))

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route
            path="/"
            element={
              <Suspense fallback={<Loading />}>
                <Dashboard />
              </Suspense>
            }
          />
          <Route
            path="/account"
            element={
              <Suspense fallback={<Loading />}>
                <Account />
              </Suspense>
            }
          />

          {/* Farmers */}
          <Route
            path="/farmers"
            element={
              <Suspense fallback={<Loading />}>
                <FarmersList />
              </Suspense>
            }
          />
          <Route
            path="/farmers/new"
            element={
              <Suspense fallback={<Loading />}>
                <NewFarmer />
              </Suspense>
            }
          />
          <Route
            path="/farmers/:id"
            element={
              <Suspense fallback={<Loading />}>
                <FarmerDetail />
              </Suspense>
            }
          />

          {/* Deliveries */}
          <Route
            path="/deliveries"
            element={
              <Suspense fallback={<Loading />}>
                <DeliveriesList />
              </Suspense>
            }
          />
          <Route
            path="/deliveries/new"
            element={
              <Suspense fallback={<Loading />}>
                <NewDelivery />
              </Suspense>
            }
          />
          <Route
            path="/deliveries/:id"
            element={
              <Suspense fallback={<Loading />}>
                <DeliveryDetail />
              </Suspense>
            }
          />

          {/* Payments */}
          <Route
            path="/payments"
            element={
              <Suspense fallback={<Loading />}>
                <PaymentsList />
              </Suspense>
            }
          />
          <Route
            path="/payments/new"
            element={
              <Suspense fallback={<Loading />}>
                <NewPayment />
              </Suspense>
            }
          />
          <Route
            path="/payments/:id"
            element={
              <Suspense fallback={<Loading />}>
                <PaymentDetail />
              </Suspense>
            }
          />

          {/* Admin-only */}
          <Route
            path="/notifications"
            element={
              <RequireRole roles={['admin']}>
                <Suspense fallback={<Loading />}>
                  <NotificationsList />
                </Suspense>
              </RequireRole>
            }
          />
          <Route
            path="/notifications/:id"
            element={
              <RequireRole roles={['admin']}>
                <Suspense fallback={<Loading />}>
                  <NotificationDetail />
                </Suspense>
              </RequireRole>
            }
          />
          <Route
            path="/produce"
            element={
              <RequireRole roles={['admin']}>
                <Suspense fallback={<Loading />}>
                  <ProduceList />
                </Suspense>
              </RequireRole>
            }
          />
          <Route
            path="/produce/new"
            element={
              <RequireRole roles={['admin']}>
                <Suspense fallback={<Loading />}>
                  <NewProduceLine />
                </Suspense>
              </RequireRole>
            }
          />
          <Route
            path="/produce/:id"
            element={
              <RequireRole roles={['admin']}>
                <Suspense fallback={<Loading />}>
                  <ProduceDetail />
                </Suspense>
              </RequireRole>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}