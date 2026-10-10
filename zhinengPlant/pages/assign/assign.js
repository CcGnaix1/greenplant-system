// pages/assign/assign.js
const api = require('../../utils/request')
const app = getApp()

Page({
  data: {
    plants: [], members: [], due: '', note: '',
    plantIdx: 0, memberIdx: 0
  },
  onLoad() {
    const today = new Date()
    const due = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-')
    Promise.all([api.call('/plant/list'), api.call('/family/info')]).then(([pRes, fRes]) => {
      this.setData({ plants: pRes.data || [], members: fRes.data.members || [], due })
    }).catch(err => wx.showToast({ title: err.message || '数据加载失败', icon: 'none' }))
  },
  onPlant(e) { this.setData({ plantIdx: Number(e.detail.value) }) },
  onMember(e) { this.setData({ memberIdx: Number(e.detail.value) }) },
  onDue(e) { this.setData({ due: e.detail.value }) },
  onNote(e) { this.setData({ note: e.detail.value }) },
  submit() {
    const plant = this.data.plants[this.data.plantIdx]
    const member = this.data.members[this.data.memberIdx]
    const familyId = app.globalData.userInfo && app.globalData.userInfo.familyId
    if (!familyId || !plant || !member) {
      wx.showToast({ title: '请先创建家庭并添加植物', icon: 'none' })
      return
    }
    api.call('/family/task/create', { data: {
      familyId,
      plantId: plant.id,
      assigneeId: member.userId,
      title: this.data.note || ('养护' + plant.name),
      due: this.data.due
    }}).then(() => {
      wx.showToast({ title: '任务已分配', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 700)
    }).catch(err => wx.showToast({ title: err.message || '分配失败', icon: 'none' }))
  }
})
