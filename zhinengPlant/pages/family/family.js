// pages/family/family.js
const api = require('../../utils/request')

Page({
  data: { fam: { members: [], tasks: [] }, isOwner: false },
  onShow() {
    const user = getApp().globalData.userInfo
    this.setData({ isOwner: !!user && user.role === 'owner' })
    this.load()
  },
  load() {
    api.call('/family/info').then(res => this.setData({ fam: res.data }))
      .catch(err => wx.showToast({ title: err.message || '家庭信息加载失败', icon: 'none' }))
  },
  createFamily() {
    api.call('/family/create', { data: { name: '我的家庭' } }).then(res => {
      const app = getApp()
      const info = Object.assign({}, app.globalData.userInfo || {}, { familyId: res.data.familyId, role: 'owner' })
      app.globalData.userInfo = info
      wx.setStorageSync('userInfo', info)
      wx.showToast({ title: '家庭创建成功', icon: 'success' })
      this.load()
    }).catch(err => wx.showToast({ title: err.message || '创建失败', icon: 'none' }))
  },
  goAddMember() {
    if (!this.data.isOwner) {
      wx.showToast({ title: '仅家庭管理员可以添加成员', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/member-add/member-add' })
  },
  goAssign() { wx.navigateTo({ url: '/pages/assign/assign' }) },
  toggleTask(e) {
    const id = e.currentTarget.dataset.id
    if (e.currentTarget.dataset.status === 'done') return
    api.call('/family/task/complete', { data: { id } }).then(() => this.load())
      .catch(err => wx.showToast({ title: err.message || '更新失败', icon: 'none' }))
  }
})
