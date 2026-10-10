// pages/record/record.js
const TYPES = ['浇水', '施肥', '修剪', '转盆', '检查', '换盆', '记一笔']
const api = require('../../utils/request')

Page({
  data: { types: TYPES, picked: '浇水', note: '' },
  onLoad(opt) { this.plantId = opt.id || 1 },
  onPick(e) { this.setData({ picked: e.currentTarget.dataset.t }) },
  onNote(e) { this.setData({ note: e.detail.value }) },
  submit() {
    const typeMap = { '浇水': 'water', '施肥': 'fertilize', '修剪': 'prune', '转盆': 'repot', '换盆': 'repot', '检查': 'check', '记一笔': 'other' }
    wx.showLoading({ title: '保存中' })
    api.call('/plant/record', { data: { id: this.plantId, type: typeMap[this.data.picked] || 'other', note: this.data.note } })
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '已记录', icon: 'success' })
        setTimeout(() => wx.navigateBack(), 600)
      })
      .catch(err => {
        wx.hideLoading()
        wx.showToast({ title: (err && err.message) || '保存失败', icon: 'none' })
      })
  }
})
