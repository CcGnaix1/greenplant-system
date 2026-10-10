// pages/scan/scan.js
const api = require('../../utils/request')

Page({
  data: { stage: 'idle', image: '', candidates: [], confidence: 0 },

  chooseImage(e) {
    const sourceType = e.currentTarget.dataset.type === 'camera'
      ? ['camera'] : ['album']
    wx.chooseMedia({
      count: 1, mediaType: ['image'], sourceType,
      success: res => {
        this.setData({ image: res.tempFiles[0].tempFilePath })
        this.recognize()
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

  recognize() {
    this.setData({ stage: 'loading' })
    api.call('/species/recognize', { image: this.data.image }).then(res => {
      const d = res.data
      // 只显示最高置信度的最终结果，不展示其他候选品种。
      const candidates = (d.candidates || []).slice(0, 1).map(c => ({
        species: c.species,
        pct: Math.round(c.confidence * 100)
      }))
      this.setData({
        stage: 'result',
        candidates,
        confidence: d.candidates && d.candidates[0] ? Math.round(d.candidates[0].confidence * 100) : 0
      })
    }).catch(err => {
      wx.showToast({ title: (err && err.message) || '识别失败，请重试', icon: 'none' })
      this.setData({ stage: 'idle' })
    })
  },

  pickSpecies(e) {
    const sp = e.currentTarget.dataset.sp
    wx.navigateTo({ url: '/pages/create/create?species=' + encodeURIComponent(sp) })
  },

  goDiagnose() {
    wx.navigateTo({ url: '/pages/diagnose/diagnose' })
  },

  retry() { this.setData({ stage: 'idle', image: '' }) }
})
