/**
 * 渠道管理 Store
 * 
 * Channels Management Store
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ref } from 'vue'

export interface ChannelConfig {
  name: string
  description: string
  icon: string
  enabled: boolean
  configured: boolean
  config: Record<string, any>
}

export interface ChannelStatus {
  enabled: boolean
  running: boolean
  display_name: string
  instances?: Record<string, ChannelInstanceStatus>
}

export interface ChannelInstanceStatus {
  enabled: boolean
  running: boolean
  display_name: string
  instance_key: string
}

export const useChannelsStore = defineStore('channels', () => {
  // 状态
  const channels: Ref<Record<string, ChannelConfig>> = ref({})
  const status: Ref<Record<string, ChannelStatus>> = ref({})
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)
  
  // 待保存的配置变更
  const pendingChanges: Ref<Record<string, Record<string, any>>> = ref({})

  // 计算属性
  const enabledChannels = computed(() => {
    return Object.entries(channels.value)
      .filter(([_, channel]) => channel.enabled)
      .map(([id, channel]) => ({ id, ...channel }))
  })

  const configuredChannels = computed(() => {
    return Object.entries(channels.value)
      .filter(([_, channel]) => channel.configured)
      .map(([id, channel]) => ({ id, ...channel }))
  })

  const runningChannels = computed(() => {
    // 只统计当前用户已启用且在运行的渠道（防止新用户看到其他用户启用的渠道状态）
    return Object.entries(channels.value)
      .filter(([id, channel]) => channel.enabled && status.value[id]?.running)
      .map(([id]) => ({ id, ...status.value[id] }))
  })

  // 方法
  async function fetchChannels() {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/channels/list')
      const data = await response.json()

      if (data.success) {
        channels.value = data.channels

        // 为每个渠道获取完整配置（替换掩码后的截断数据）
        const channelIds = Object.keys(data.channels)
        await Promise.all(
          channelIds.map(async (channelId) => {
            try {
              const configResponse = await fetch(`/api/channels/my/${channelId}/config?account_id=default`)
              const configData = await configResponse.json()

              if (configData.success && configData.config) {
                // 用完整配置替换掩码后的配置
                channels.value[channelId].config = configData.config

                // 同时修正 enabled 状态（从数据库读取的真实值）
                const accountIndex = data.channels[channelId].accounts?.findIndex(
                  (a: any) => a.account_id === 'default'
                )
                if (accountIndex !== undefined && accountIndex >= 0) {
                  data.channels[channelId].accounts[accountIndex].config = configData.config
                }
              }
            } catch (e) {
              console.error(`Failed to fetch full config for ${channelId}:`, e)
            }
          })
        )
      } else {
        error.value = data.error || 'Failed to fetch channels'
      }
    } catch (e: any) {
      error.value = e.message || 'Network error'
      console.error('Error fetching channels:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    try {
      const response = await fetch('/api/channels/status')
      const data = await response.json()

      if (data.success) {
        status.value = data.status
      }
    } catch (e: any) {
      console.error('Error fetching channel status:', e)
    }
  }

  async function testChannel(
    channelId: string,
    config?: Record<string, any>,
    accountId?: string
  ): Promise<{ success: boolean; message: string; data?: any }> {
    error.value = null

    try {
      const response = await fetch('/api/channels/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          channel: channelId,
          config,
          account_id: accountId
        })
      })

      const data = await response.json()
      return data
    } catch (e: any) {
      error.value = e.message || 'Test failed'
      return {
        success: false,
        message: e.message || 'Network error'
      }
    }
  }

  async function updateChannelConfig(
    channelId: string,
    config: Record<string, any>,
    accountId: string = 'default',
    isEnabled: boolean = false
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await fetch('/api/channels/my/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          channel: channelId,
          account_id: accountId,
          config,
          is_enabled: isEnabled
        })
      })

      const data = await response.json()

      if (data.success) {
        // 重新获取渠道列表
        await fetchChannels()
        return true
      } else {
        error.value = data.message || 'Update failed'
        return false
      }
    } catch (e: any) {
      error.value = e.message || 'Network error'
      console.error('Error updating channel config:', e)
      return false
    } finally {
      loading.value = false
    }
  }
  
  // 更新本地渠道配置（不立即保存到后端）
  function updateLocalChannelConfig(channelId: string, config: Record<string, any>) {
    const nextConfig = JSON.parse(JSON.stringify(config))
    if (channels.value[channelId]) {
      channels.value[channelId].config = nextConfig
      pendingChanges.value[channelId] = nextConfig
    }
  }
  
  // 批量保存所有渠道配置
  async function saveAllChannels(): Promise<boolean> {
    if (Object.keys(pendingChanges.value).length === 0) {
      return true
    }

    loading.value = true
    error.value = null

    try {
      // 批量保存所有变更的渠道配置
      const promises = Object.entries(pendingChanges.value).map(([channelId, config]) => {
        // 从配置中读取 account_id 和 enabled 状态，支持多账号
        const accountId = String(config.account_id || 'default')
        const isEnabled = config.enabled === true || (
          config.accounts && Object.values(config.accounts).some((a: any) => a.enabled === true)
        )

        return fetch('/api/channels/my/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            channel: channelId,
            account_id: accountId,
            config,
            is_enabled: isEnabled
          })
        })
      })

      const results = await Promise.all(promises)
      const allSuccess = results.every(r => r.ok)

      if (allSuccess) {
        pendingChanges.value = {}
        await fetchChannels() // 重新加载
        return true
      } else {
        error.value = 'Some channel configurations failed to save'
        return false
      }
    } catch (e: any) {
      error.value = e.message || 'Network error'
      console.error('Error saving channels:', e)
      return false
    } finally {
      loading.value = false
    }
  }
  
  // 检查是否有未保存的变更
  function hasUnsavedChanges(): boolean {
    return Object.keys(pendingChanges.value).length > 0
  }
  
  // 清除待保存的变更
  function clearPendingChanges() {
    pendingChanges.value = {}
  }

  async function getChannelConfig(channelId: string, accountId: string = 'default'): Promise<Record<string, any> | null> {
    try {
      const response = await fetch(`/api/channels/my/${channelId}/config?account_id=${accountId}`)
      const data = await response.json()

      if (data.success) {
        return data.config
      }
      return null
    } catch (e: any) {
      console.error('Error getting channel config:', e)
      return null
    }
  }

  // 初始化
  function init() {
    fetchChannels()
    fetchStatus()

    // 定期更新状态
    setInterval(() => {
      fetchStatus()
    }, 10000) // 每 10 秒更新一次
  }

  return {
    // 状态
    channels,
    status,
    loading,
    error,

    // 计算属性
    enabledChannels,
    configuredChannels,
    runningChannels,

    // 方法
    fetchChannels,
    fetchStatus,
    testChannel,
    updateChannelConfig,
    updateLocalChannelConfig,
    saveAllChannels,
    hasUnsavedChanges,
    clearPendingChanges,
    getChannelConfig,
    init
  }
})
