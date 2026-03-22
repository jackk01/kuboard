import { defineStore } from 'pinia'

import { apiRequest } from '../lib/api'
import type { Cluster } from '../types'

interface ClusterPayload {
  name: string
  environment: string
  description: string
  kubeconfig: string
  server_override?: string
}

export const useClusterStore = defineStore('clusters', {
  state: () => ({
    items: [] as Cluster[],
    loading: false,
    saving: false,
    updatingIds: [] as string[],
    deletingIds: [] as string[],
  }),

  actions: {
    async fetchClusters() {
      this.loading = true
      try {
        this.items = await apiRequest<Cluster[]>('/api/v1/clusters')
      } finally {
        this.loading = false
      }
    },

    async importCluster(payload: ClusterPayload) {
      this.saving = true
      try {
        const created = await apiRequest<Cluster>('/api/v1/clusters', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        this.items = [created, ...this.items]
        return created
      } finally {
        this.saving = false
      }
    },

    async healthCheck(clusterId: string) {
      const updated = await apiRequest<Cluster>(`/api/v1/clusters/${clusterId}/health-check`, {
        method: 'POST',
      })
      this.items = this.items.map((item) => (item.id === clusterId ? updated : item))
    },

    async updateCluster(
      clusterId: string,
      payload: {
        name: string
        environment: string
        description: string
      },
    ) {
      this.updatingIds = [...this.updatingIds, clusterId]
      try {
        const updated = await apiRequest<Cluster>(`/api/v1/clusters/${clusterId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        })
        this.items = this.items.map((item) => (item.id === clusterId ? updated : item))
        return updated
      } finally {
        this.updatingIds = this.updatingIds.filter((id) => id !== clusterId)
      }
    },

    async deleteCluster(clusterId: string) {
      this.deletingIds = [...this.deletingIds, clusterId]
      try {
        await apiRequest<void>(`/api/v1/clusters/${clusterId}`, {
          method: 'DELETE',
        })
        this.items = this.items.filter((item) => item.id !== clusterId)
      } finally {
        this.deletingIds = this.deletingIds.filter((id) => id !== clusterId)
      }
    },
  },
})
