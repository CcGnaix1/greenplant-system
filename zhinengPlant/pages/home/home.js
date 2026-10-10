// pages/home/home.js
const api = require('../../utils/request')
const app = getApp()

Page({
  data: {
    greeting: '早上好',
    userName: '绿植主人',
    plants: [],
    careDue: [],
    familyTasks: [],
    completingId: 0
  },

  onShow() {
    const h = new Date().getHours()
    const greeting = h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'
    const user = app.globalData.userInfo
    this.setData({ greeting, userName: user ? user.name : '绿植主人' })
    if (!user) {
      this.setData({ plants: [], careDue: [], familyTasks: [] })
      return
    }
    api.call('/plant/list').then(res => {
      const plants = res.data
      this.setData({
        plants,
        careDue: plants.filter(p => p.status !== 'ok')
      })
    }).catch(() => {})
    this.loadFamilyTasks()
  },

  loadFamilyTasks() {
    const user = app.globalData.userInfo
    if (!user || !user.familyId) {
      this.setData({ familyTasks: [] })
      return
    }
    api.call('/family/task/mine', { data: {
      familyId: user.familyId,
      mine: true,
      status: 'todo'
    }}).then(res => {
      const tasks = (res.data || []).map(item => Object.assign({}, item, {
        dueText: this.formatDue(item.due)
      }))
      this.setData({ familyTasks: tasks })
    }).catch(() => this.setData({ familyTasks: [] }))
  },

  formatDue(due) {
    if (!due) return '未设置截止日期'
    const today = new Date()
    const y = today.getFullYear()
    const m = String(today.getMonth() + 1).padStart(2, '0')
    const d = String(today.getDate()).padStart(2, '0')
    const todayText = [y, m, d].join('-')
    if (due === todayText) return '今天截止'
    return due + ' 截止'
  },

  completeFamilyTask(e) {
    const id = Number(e.currentTarget.dataset.id)
    if (!id || this.data.completingId) return
    this.setData({ completingId: id })
    api.call('/family/task/complete', { data: { id } }).then(() => {
      this.setData({
        familyTasks: this.data.familyTasks.filter(item => item.id !== id),
        completingId: 0
      })
      wx.showToast({ title: '任务已完成', icon: 'success' })
    }).catch(err => {
      this.setData({ completingId: 0 })
      wx.showToast({ title: err.message || '操作失败', icon: 'none' })
    })
  },

  waterAll() {
    const plants = this.data.plants
    if (!plants.length) {
      wx.showToast({ title: '还没有植物', icon: 'none' })
      return
    }
    if (require('../../utils/request').MOCK) {
      wx.showToast({ title: '已为所有缺水植物浇水', icon: 'success' })
      return
    }
    // 真实模式：逐盆调用浇水接口
    const tasks = plants.map(p => api.call('/plant/water', { data: { id: p.id } }).catch(() => null))
    wx.showLoading({ title: '浇水ing' })
    Promise.all(tasks).then(() => {
      wx.hideLoading()
      wx.showToast({ title: '已浇 ' + plants.length + ' 盆', icon: 'success' })
      this.onShow()
    })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/detail/detail?id=' + e.currentTarget.dataset.id })
  },
  goCreate() {
    wx.navigateTo({ url: '/pages/create/create' })
  },
  goScan() {
    wx.switchTab({ url: '/pages/scan/scan' })
  },
  goKb() {
    wx.switchTab({ url: '/pages/kb/kb' })
  },
  goPlan() {
    wx.navigateTo({ url: '/pages/plan/plan' })
  },
  goRecord(e) {
    wx.navigateTo({ url: '/pages/record/record?id=' + e.currentTarget.dataset.id })
  },
  goDiagnose() {
    wx.navigateTo({ url: '/pages/diagnose/diagnose' })
  },
  goStats() {
    wx.navigateTo({ url: '/pages/stats/stats' })
  }
})
