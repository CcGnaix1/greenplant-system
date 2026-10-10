// pages/diagnose/diagnose.js
const api = require('../../utils/request')

Page({
  data: { stage: 'idle', image: '', report: null, diagnosisId: null },

  chooseImage(e) {
    const sourceType = e.currentTarget.dataset.type === 'camera' ? ['camera'] : ['album']
    wx.chooseMedia({
      count: 1, mediaType: ['image'], sourceType,
      success: res => {
        this.setData({ image: res.tempFiles[0].tempFilePath })
        this.analyze()
      },
      fail: err => {
        if (err && /cancel/i.test(err.errMsg || '')) return
        wx.showModal({
          title: '无法使用相机',
          content: '请在微信设置中允许小程序使用相机，然后重试。',
          confirmText: '去设置',
          success: res => { if (res.confirm) wx.openSetting() }
        })
      }
    })
  },

  analyze() {
    this.setData({ stage: 'loading' })
    // 真实模式：上传照片到后端 /diagnosis（multipart 字段 image），返回诊断报告
    api.call('/diagnose/submit', { image: this.data.image }).then(res => {
      this.setData({ stage: 'done', report: res.data, diagnosisId: res.data.diagnosisId })
    }).catch(err => {
      wx.showToast({ title: (err && err.message) || '诊断失败，请重试', icon: 'none' })
      this.setData({ stage: 'idle' })
    })
  },

  feedback(e) {
    const ok = e.currentTarget.dataset.ok
    if (!this.data.diagnosisId) return
    api.call('/diagnose/feedback', {
      data: { id: this.data.diagnosisId, ok }
    }).then(() => {
      wx.showToast({ title: ok ? '感谢反馈' : '已记录纠错', icon: 'success' })
    }).catch(err => {
      wx.showToast({ title: (err && err.message) || '反馈失败', icon: 'none' })
    })
  },

  reset() { this.setData({ stage: 'idle', image: '', report: null, diagnosisId: null }) }
})
