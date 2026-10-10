const api = require('../../utils/request')
const app = getApp()

Page({
  data: { phone: '', duty: '', loading: false },
  onPhone(e) {
    this.setData({ phone: e.detail.value.replace(/\D/g, '').slice(0, 11) })
  },
  onDuty(e) {
    this.setData({ duty: e.detail.value })
  },
  submit() {
    if (this.data.loading) return
    const phone = this.data.phone.trim()
    const user = app.globalData.userInfo
    if (!user || !user.familyId) {
      wx.showToast({ title: '请先创建家庭', icon: 'none' })
      return
    }
    if (user.role !== 'owner') {
      wx.showToast({ title: '仅家庭管理员可以添加成员', icon: 'none' })
      return
    }
    if (!/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确的11位手机号', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    api.call('/family/member/add', { data: {
      familyId: user.familyId,
      phone,
      role: 'member',
      duty: this.data.duty.trim() || '共同养护'
    }}).then(res => {
      wx.showToast({ title: '已添加' + (res.data.nickname || '成员'), icon: 'success' })
      setTimeout(() => wx.navigateBack(), 700)
    }).catch(err => {
      wx.showToast({ title: err.message || '添加失败', icon: 'none' })
      this.setData({ loading: false })
    })
  }
})
