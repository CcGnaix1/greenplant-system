// pages/mine/mine.js
const api = require('../../utils/request')
const app = getApp()

Page({
  data: { user: null, unread: 0 },
  onShow() {
    const user = app.globalData.userInfo
    this.setData({ user, unread: 0 })
    if (!user) return
    api.call('/notification/list').then(res => {
      this.setData({ unread: res.data.filter(n => !n.read).length })
    }).catch(() => {})
  },
  openLogin() {
    wx.navigateTo({
      url: '/pages/login/login',
      fail: err => {
        console.error('打开登录页失败', err)
        wx.showToast({ title: '登录页打开失败，请重新编译', icon: 'none' })
      }
    })
  },
  goLogin() { this.openLogin() },
  switchAccount() { this.openLogin() },
  goFamily() { wx.navigateTo({ url: '/pages/family/family' }) },
  goPlan() { wx.navigateTo({ url: '/pages/plan/plan' }) },
  goDiagnose() { wx.navigateTo({ url: '/pages/diagnose/diagnose' }) },
  goExport() { wx.navigateTo({ url: '/pages/export/export' }) },
  goTimeline() { wx.navigateTo({ url: '/pages/timeline/timeline' }) },
  changeAvatar() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'],
      success: res => {
        const filePath = res.tempFiles[0].tempFilePath
        wx.showLoading({ title: '正在上传' })
        api.call('/user/avatar', { image: filePath }).then(result => {
          const base = app.globalData.baseUrl.replace(/\/api\/?$/, '')
          const stored = result.data.avatarUrl || ''
          const avatarUrl = /^https?:\/\//.test(stored) ? stored : base + stored
          const user = Object.assign({}, app.globalData.userInfo, { avatarUrl })
          app.globalData.userInfo = user
          wx.setStorageSync('userInfo', user)
          this.setData({ user })
          wx.showToast({ title: '头像已更新', icon: 'success' })
        }).catch(err => {
          wx.showToast({ title: (err && err.message) || '头像上传失败', icon: 'none' })
        }).finally(() => wx.hideLoading())
      }
    })
  },
  logout() {
    app.logout()
    this.setData({ user: null })
    wx.showToast({ title: '已退出登录', icon: 'success' })
  }
})
